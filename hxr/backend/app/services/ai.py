"""AI 问答服务 —— 治理规则的落地。

**四条不可让步的规则（对应《公共层契约》§4）**：

1. **回答必须带引用。** `AIMessage.has_citation=False` 时前端不展示。
   没有引用的 AI 回答不允许给用户看 —— 这是防幻觉的机制，不是建议。

2. **检索先过权限过滤，再检索。**
   由 retrieval.py 在 SQL 层完成，本模块不重复做。

3. **会话上下文严格限定在当前项目。**
   内部试用期不允许跨项目检索，哪怕同一个人有多个项目权限。
   例外：跨项目知识库（已沉淀的通用经验）是刻意共享的。

4. **回答强制四段式**：结论 / 依据 / 不确定性 / 责任声明。
   缺任一段视为无效回答。
   其中「不确定性」是**主动暴露风险**，不是免责话术 ——
   比如"该参数来源刚更新、尚未人工复核"必须说出来。

另外：所有 prompt / 回答 / 引用 / 反馈入库，保留 ≥ 90 天供审查。
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models.ai import AICitation, AIConversation, AIMessage
from app.models.enums import STAGE_LABELS, StageCode
from app.services import llm as llm_svc
from app.services.retrieval import RetrievedChunk, search

logger = logging.getLogger("app.ai")

DISCLAIMER = "本回答由 AI 辅助生成，仅供设计参考，须由注册工程师复核确认"

# 系统提示词。**要点是把模型的角色限定为"组织语言"而不是"提供事实"**，
# 事实全部来自检索片段，这样幻觉从机制上被压到最低。
SYSTEM_PROMPT = """你是桩基工程领域的设计辅助助手，服务于设计院内部试用系统。

【最高原则】
1. 你只能依据下面提供的【检索片段】作答。片段里没有的内容，绝对不许补充或推测。
2. 如果片段不足以回答，必须明确说"检索到的资料不足以回答该问题"，并说明还缺什么。
3. 不许编造规范条文号、页码、表号、数值。引用只能引用片段里出现过的定位信息。
4. 你是辅助角色，不做设计决定。需要工程师判断的地方要明确指出来。

【输出格式】必须严格按下面四段输出，缺一不可：

【结论】
直接回答用户的问题。如果资料不足，就写"检索到的资料不足以回答"。

【依据】
逐条列出你依据的片段，每条注明来源（文件名称 + 版本 + 页码/表号/章节）。
只列你真正用到的，不要凑数。

【不确定性】
主动说明：资料是否充分、是否有相互矛盾的片段、
涉及参数是否尚未人工复核、哪些地方需要工程师判断。
这一项**不是免责话术**，是真的要指出风险。如果没有不确定的地方，写"未发现明显不确定项"。

【责任声明】
本回答由 AI 辅助生成，仅供设计参考，须由注册工程师复核确认。

【语言】用中文，简洁专业，避免空话。"""


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ============================================================
# 上下文构建
# ============================================================


def build_context(chunks: list[RetrievedChunk], max_chars: int = 6000) -> str:
    """把检索片段拼成模型可用的上下文。

    每条都带编号与定位，便于模型在【依据】里引用。
    """
    if not chunks:
        return "（没有检索到任何相关片段）"

    parts: list[str] = []
    total = 0
    for i, c in enumerate(chunks, 1):
        head = f"[片段{i}] 来源：{c.locator or '未知'}"
        if c.source_type == "KNOWLEDGE_BASE":
            head += "（跨项目知识库·已闭环经验）"
        block = f"{head}\n{c.text.strip()}"
        if total + len(block) > max_chars:
            break
        parts.append(block)
        total += len(block)
    return "\n\n".join(parts)


# ============================================================
# 四段式解析
# ============================================================

_SECTION_NAMES = ("结论", "依据", "不确定性", "责任声明")
# 逐个段落切开：以【段名】为分隔符。
# 之前用"全可选组的正则"会失败 —— 第一个 .*? 会直接匹配到末尾，
# 后面的可选组全部跳过。分成两步做更可靠。
_SECTION_SPLIT_RE = re.compile(r"【(结论|依据|不确定性|责任声明)】")

_KEY_MAP = {
    "结论": "conclusion",
    "依据": "basis",
    "不确定性": "uncertainty",
    "责任声明": "disclaimer",
}


def parse_sections(text: str) -> dict:
    """解析四段式回答。

    容错：模型可能漏段或用近似措辞。能解析出哪段就存哪段，
    但**是否完整**由 `is_complete` 标出，前端据此提示。
    """
    out = {
        "conclusion": None,
        "basis": None,
        "uncertainty": None,
        "disclaimer": None,
        "is_complete": False,
    }
    if not text:
        return out

    parts = _SECTION_SPLIT_RE.split(text)
    # split 结果形如 ['前置文字', '结论', '内容', '依据', '内容', ...]
    if len(parts) < 3:
        # 完全没按格式 —— 整段放结论，但标注不完整
        out["conclusion"] = text.strip()
        out["disclaimer"] = DISCLAIMER
        return out

    for i in range(1, len(parts) - 1, 2):
        name = parts[i]
        body = (parts[i + 1] or "").strip()
        key = _KEY_MAP.get(name)
        if key and body:
            out[key] = body

    if not out["disclaimer"]:
        out["disclaimer"] = DISCLAIMER
    out["is_complete"] = bool(out["conclusion"] and out["basis"] and out["uncertainty"])
    return out


# ============================================================
# 会话
# ============================================================


def get_or_create_conversation(
    db: Session,
    *,
    project_id: str,
    user_id: str,
    conv_id: str | None = None,
    stage_code: str | None = None,
    title: str | None = None,
    max_secret_level: int = 2,
) -> AIConversation:
    """取会话；不存在则新建。

    **会话强制绑定 project_id** —— 内部试用期不允许跨项目。
    scope_snapshot 记录创建时的可检索范围，避免权限变更后越权：
    即使后来该用户被调离项目，历史会话仍按当时范围回答。
    """
    if conv_id:
        conv = db.get(AIConversation, conv_id)
        if conv is not None:
            if conv.project_id != project_id:
                from fastapi import HTTPException, status as http_status

                raise HTTPException(
                    status_code=http_status.HTTP_403_FORBIDDEN,
                    detail={"code": 3002, "message": "该会话属于其他项目，不能跨项目继续"},
                )
            if conv.user_id != user_id:
                from fastapi import HTTPException, status as http_status

                raise HTTPException(
                    status_code=http_status.HTTP_403_FORBIDDEN,
                    detail={"code": 3002, "message": "该会话属于其他用户"},
                )
            return conv

    conv = AIConversation(
        project_id=project_id,
        user_id=user_id,
        stage_code=stage_code,
        title=title or "新会话",
        scope_snapshot={
            "project_id": project_id,
            "stage_code": stage_code,
            "max_secret_level": max_secret_level,
            "allow_cross_project": settings.AI_ALLOW_CROSS_PROJECT,
            "created_at": _now().isoformat(),
        },
        message_count=0,
    )
    db.add(conv)
    db.flush()
    return conv


# ============================================================
# 问答主流程
# ============================================================


def ask(
    db: Session,
    *,
    project_id: str,
    user_id: str,
    question: str,
    conv_id: str | None = None,
    stage_code: str | None = None,
    discipline: str | None = None,
    max_secret_level: int = 2,
    include_knowledge_base: bool = True,
) -> dict:
    """提一个问题并返回四段式回答。

    流程：
        1. 建/取会话（限定项目）
        2. **检索（权限过滤在前）**
        3. 组装上下文 → 调模型
        4. 解析四段式
        5. 落库引用
        6. 返回结果（含 has_citation —— 无引用时前端不展示）
    """
    question = (question or "").strip()
    if not question:
        from fastapi import HTTPException, status as http_status

        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail={"code": 1001, "message": "问题不能为空"},
        )

    conv = get_or_create_conversation(
        db,
        project_id=project_id,
        user_id=user_id,
        conv_id=conv_id,
        stage_code=stage_code,
        title=question[:40],
        max_secret_level=max_secret_level,
    )

    # 记录用户提问
    user_msg = AIMessage(
        conversation_id=conv.id,
        project_id=project_id,
        role="user",
        content=question,
    )
    db.add(user_msg)
    db.flush()

    # ---- 检索：权限过滤在 SQL 层完成，不是拿到结果后再筛 ----
    chunks = search(
        db,
        project_id=project_id,
        query=question,
        stage_code=stage_code,
        max_secret_level=max_secret_level,
        include_knowledge_base=include_knowledge_base,
        limit=8,
    )

    context = build_context(chunks)
    stage_hint = ""
    if stage_code:
        try:
            stage_hint = f"当前阶段：{STAGE_LABELS[StageCode(stage_code)]}\n"
        except (ValueError, KeyError):
            stage_hint = f"当前阶段：{stage_code}\n"

    user_prompt = (
        f"{stage_hint}"
        f"用户问题：{question}\n\n"
        f"【检索片段】\n{context}\n\n"
        f"请严格按四段式格式作答。"
    )

    provider = llm_svc.get_provider()
    reply = provider.complete(system=SYSTEM_PROMPT, user=user_prompt, max_tokens=1500)

    # ---- 组装回答 ----
    if reply.degraded:
        # 降级时**不编造答案**，只把检索到的原文交给用户
        answer_text = _degraded_answer(question, chunks, reply.degrade_reason)
        sections = parse_sections(answer_text)
        sections["is_complete"] = bool(chunks)   # 有原文就算可用信息
    else:
        sections = parse_sections(reply.text)
        answer_text = reply.text

    # ---- 引用落库。**没有引用就不许展示** ----
    has_citation = len(chunks) > 0

    ai_msg = AIMessage(
        conversation_id=conv.id,
        project_id=project_id,
        role="assistant",
        content=answer_text,
        conclusion=sections.get("conclusion"),
        uncertainty=sections.get("uncertainty"),
        disclaimer=sections.get("disclaimer") or DISCLAIMER,
        has_citation=has_citation,
        model=reply.model,
        provider=reply.provider,
        prompt_tokens=reply.prompt_tokens,
        completion_tokens=reply.completion_tokens,
        latency_ms=reply.latency_ms,
        error=reply.degrade_reason if reply.degraded else None,
    )
    db.add(ai_msg)
    db.flush()

    for i, c in enumerate(chunks):
        db.add(
            AICitation(
                message_id=ai_msg.id,
                chunk_id=c.chunk_id,
                source_version_id=c.source_version_id,
                locator=c.locator,
                quoted_text=c.text[:600],
                score=c.score,
                sort=i,
            )
        )

    conv.message_count = (conv.message_count or 0) + 2
    if conv.title in (None, "", "新会话"):
        conv.title = question[:40]
    db.flush()

    return {
        "conversation_id": conv.id,
        "message_id": ai_msg.id,
        "question": question,
        "content": answer_text,
        "conclusion": sections.get("conclusion"),
        "basis": sections.get("basis"),
        "uncertainty": sections.get("uncertainty"),
        "disclaimer": sections.get("disclaimer") or DISCLAIMER,
        "is_complete": sections.get("is_complete", False),
        "has_citation": has_citation,
        "degraded": reply.degraded,
        "degrade_reason": reply.degrade_reason,
        "provider": reply.provider,
        "model": reply.model,
        "latency_ms": reply.latency_ms,
        "citations": [c.to_citation() for c in chunks],
    }


def _degraded_answer(
    question: str, chunks: list[RetrievedChunk], reason: str | None
) -> str:
    """未配置模型时的诚实回答。

    **不编造内容**，只把检索到的原文交出来。
    这比编一段像模像样的话诚实得多，也不会污染设计判断。
    """
    if not chunks:
        return (
            f"【结论】\n未配置 AI 模型，且未检索到相关资料，无法回答该问题。\n\n"
            f"【依据】\n无。\n\n"
            f"【不确定性】\n{reason or 'AI 未配置'}。"
            f"请由工程师依据规范与勘察报告人工判断。\n\n"
            f"【责任声明】\n{DISCLAIMER}"
        )

    # 结论行不要重复"未配置 AI 模型" —— reason 里往往已经说了
    lines = [
        "【结论】",
        f"未生成归纳性回答，以下是与你问题最相关的原文片段，请自行阅读判断。",
        f"（原因：{reason or 'LLM_PROVIDER=none'}）",
        "",
        "【依据】",
    ]
    for i, c in enumerate(chunks[:5], 1):
        lines.append(f"{i}. {c.locator or '未知来源'}")
    lines += [
        "",
        "【不确定性】",
        "以上为原文摘录，未经模型归纳，也未做交叉核对。"
        "配置模型后（改 LLM_PROVIDER 与 LLM_BASE_URL 即可）可获得归纳性回答。",
        "",
        "【责任声明】",
        DISCLAIMER,
    ]
    return "\n".join(lines)


# ============================================================
# 查询
# ============================================================


def list_conversations(
    db: Session, *, project_id: str, user_id: str, limit: int = 50
) -> list[AIConversation]:
    return list(
        db.execute(
            select(AIConversation)
            .where(
                AIConversation.project_id == project_id,
                AIConversation.user_id == user_id,
                AIConversation.archived.is_(False),
            )
            .order_by(AIConversation.updated_at.desc())
            .limit(limit)
        ).scalars().all()
    )


def get_messages(db: Session, *, conversation_id: str, limit: int = 200) -> list[AIMessage]:
    return list(
        db.execute(
            select(AIMessage)
            .where(AIMessage.conversation_id == conversation_id)
            .order_by(AIMessage.created_at)
            .limit(limit)
        ).scalars().all()
    )


def citations_of(db: Session, message_id: str) -> list[AICitation]:
    return list(
        db.execute(
            select(AICitation)
            .where(AICitation.message_id == message_id)
            .order_by(AICitation.sort)
        ).scalars().all()
    )


def set_feedback(
    db: Session, *, message_id: str, user_id: str, feedback: str, note: str | None = None
) -> AIMessage:
    """记录用户反馈。用于后续评估检索质量。"""
    msg = db.get(AIMessage, message_id)
    if msg is None:
        from fastapi import HTTPException, status as http_status

        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail={"code": 4004, "message": "消息不存在"},
        )
    conv = db.get(AIConversation, msg.conversation_id)
    if conv is None or conv.user_id != user_id:
        from fastapi import HTTPException, status as http_status

        raise HTTPException(
            status_code=http_status.HTTP_403_FORBIDDEN,
            detail={"code": 3002, "message": "只能对自己的会话给出反馈"},
        )
    if feedback not in ("USEFUL", "USELESS"):
        from fastapi import HTTPException, status as http_status

        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail={"code": 1001, "message": "反馈取值只能是 USEFUL 或 USELESS"},
        )

    msg.feedback = feedback
    msg.feedback_note = note
    db.flush()
    return msg


def message_out(db: Session, msg: AIMessage) -> dict:
    cites = citations_of(db, msg.id)
    return {
        "id": msg.id,
        "role": msg.role,
        "content": msg.content,
        "conclusion": msg.conclusion,
        "uncertainty": msg.uncertainty,
        "disclaimer": msg.disclaimer,
        "has_citation": msg.has_citation,
        "model": msg.model,
        "provider": msg.provider,
        "latency_ms": msg.latency_ms,
        "error": msg.error,
        "feedback": msg.feedback,
        "feedback_note": msg.feedback_note,
        "created_at": msg.created_at,
        "citations": [
            {
                "id": c.id,
                "source_version_id": c.source_version_id,
                "locator": c.locator,
                "quoted_text": c.quoted_text,
                "score": c.score,
            }
            for c in cites
        ],
    }
