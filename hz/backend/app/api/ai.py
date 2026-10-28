"""AI 问答接口。

**四条治理规则的落地位置（对应《公共层契约》§4）**：

1. 回答必须带引用 —— `has_citation=False` 时前端不展示
2. 检索先过权限过滤，再检索 —— 权限过滤在 retrieval.py 的 SQL 层
3. 会话严格限定在当前项目 —— 会话表强制绑 project_id，
   跨项目继续会话直接 403
4. 回答强制四段式 —— 结论 / 依据 / 不确定性 / 责任声明

另外提供"知识库索引"接口：只有 `PUBLISHED` 版本能入库，
草稿与审批中的内容不该被 AI 引用。
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from app.api.deps import CurrentPrincipal, DbSession, require_project_view
from app.models.enums import STAGE_LABELS, PermissionAction, StageCode
from app.schemas import (
    AIAnswerOut,
    AIAskIn,
    AICitationOut,
    AIConversationOut,
    AIFeedbackIn,
    AIMessageOut,
    AIProviderStatusOut,
    ApiResponse,
    KnowledgeIndexIn,
)
from app.services import ai as ai_svc
from app.services import llm as llm_svc
from app.services import retrieval as ret_svc

router = APIRouter(prefix="/ai", tags=["AI 问答"])


@router.get("/provider-status", response_model=ApiResponse[AIProviderStatusOut],
            summary="AI 提供方状态")
def provider_status(principal: CurrentPrincipal) -> ApiResponse[AIProviderStatusOut]:
    """当前 AI 配置状态。

    前端据此显示「AI 未配置，仅返回检索原文」之类的诚实提示，
    而不是假装 AI 可用。
    """
    return ApiResponse(data=AIProviderStatusOut(**llm_svc.provider_status()))


@router.post("/projects/{project_id}/ask", response_model=ApiResponse[AIAnswerOut],
             summary="提问")
def ask(
    project_id: str, body: AIAskIn, db: DbSession, principal: CurrentPrincipal
) -> ApiResponse[AIAnswerOut]:
    """提问并获取四段式回答。

    **检索只覆盖你有权查看的内容**（按角色的敏感等级上限过滤，在 SQL 层完成）。
    回答一定带引用；没有引用的回答前端不会展示。
    """
    require_project_view(project_id, principal)

    # 敏感等级上限由权限引擎给出 —— 检索时会用它过滤
    max_secret = principal.max_secret_level(project_id)

    result = ai_svc.ask(
        db,
        project_id=project_id,
        user_id=principal.user_id,
        question=body.question,
        conv_id=body.conversation_id,
        stage_code=body.stage_code.value if body.stage_code else None,
        discipline=body.discipline,
        max_secret_level=max_secret,
        include_knowledge_base=body.include_knowledge_base,
    )

    from app.api.documents import _audit

    _audit(db, principal, "AI_ASK", "ai_message", result["message_id"],
           body.question[:120], project_id, None)
    db.commit()

    return ApiResponse(
        data=AIAnswerOut(**result),
        message=result.get("degrade_reason") or None,
    )


@router.get("/projects/{project_id}/conversations",
            response_model=ApiResponse[list[AIConversationOut]], summary="我的会话列表")
def list_conversations(
    project_id: str, db: DbSession, principal: CurrentPrincipal
) -> ApiResponse[list[AIConversationOut]]:
    require_project_view(project_id, principal)
    rows = ai_svc.list_conversations(db, project_id=project_id, user_id=principal.user_id)
    return ApiResponse(data=[AIConversationOut.model_validate(r) for r in rows])


@router.get("/conversations/{conversation_id}/messages",
            response_model=ApiResponse[list[AIMessageOut]], summary="会话消息")
def get_messages(
    conversation_id: str, db: DbSession, principal: CurrentPrincipal
) -> ApiResponse[list[AIMessageOut]]:
    """取会话全部消息（含引用）。

    只能看自己的会话 —— 内部试用期不做会话共享。
    """
    from app.models.ai import AIConversation

    conv = db.get(AIConversation, conversation_id)
    if conv is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": 4004, "message": "会话不存在"},
        )
    require_project_view(conv.project_id, principal)
    if conv.user_id != principal.user_id and not principal.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": 3002, "message": "只能查看自己的会话"},
        )

    msgs = ai_svc.get_messages(db, conversation_id=conversation_id)
    return ApiResponse(data=[AIMessageOut(**ai_svc.message_out(db, m)) for m in msgs])


@router.post("/messages/{message_id}/feedback", response_model=ApiResponse[dict],
             summary="对回答给出反馈")
def feedback(
    message_id: str, body: AIFeedbackIn, db: DbSession, principal: CurrentPrincipal
) -> ApiResponse[dict]:
    """反馈用于评估检索质量 —— 这是后续优化 RAG 效果的数据来源。"""
    msg = ai_svc.set_feedback(
        db,
        message_id=message_id,
        user_id=principal.user_id,
        feedback=body.feedback,
        note=body.note,
    )
    db.commit()
    return ApiResponse(data={"message_id": msg.id, "feedback": msg.feedback})


@router.post("/projects/{project_id}/knowledge/index", response_model=ApiResponse[dict],
             summary="把已发布版本切片入知识库")
def index_version(
    project_id: str, body: KnowledgeIndexIn, db: DbSession, principal: CurrentPrincipal
) -> ApiResponse[dict]:
    """把某个**已发布**版本的内容切片入知识库，供后续检索。

    **只有 PUBLISHED 版本能入库** —— 草稿和审批中的内容不该被 AI 引用。
    """
    require_project_view(project_id, principal)

    # 索引属于写操作，要求 EDIT 权限
    from app.api.deps import require_action

    require_action(principal, PermissionAction.EDIT, project_id, None)

    from app.models.document import DocumentVersion

    v = db.get(DocumentVersion, body.version_id)
    if v is None or v.project_id != project_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": 4004, "message": "文件版本不存在或不属于本项目"},
        )

    chunks = ret_svc.index_document_version(db, version_id=body.version_id)
    db.commit()
    return ApiResponse(
        data={"version_id": body.version_id, "chunk_count": len(chunks)},
        message=f"已索引 {len(chunks)} 个知识块",
    )


@router.get("/projects/{project_id}/retrieve", response_model=ApiResponse[list[AICitationOut]],
            summary="仅检索（不生成回答）")
def retrieve_only(
    project_id: str,
    db: DbSession,
    principal: CurrentPrincipal,
    q: str,
    stage: str | None = None,
    limit: int = 8,
) -> ApiResponse[list[AICitationOut]]:
    """只做检索，不调模型。

    两个用途：
      1. 调试检索质量（AI 回答不准，先看检索到不到对的东西）
      2. 前端"引用溯源"—— 让用户直接看原文，不经过模型
    """
    require_project_view(project_id, principal)

    chunks = ret_svc.search(
        db,
        project_id=project_id,
        query=q,
        stage_code=stage,
        max_secret_level=principal.max_secret_level(project_id),
        limit=limit,
    )
    return ApiResponse(
        data=[AICitationOut(**c.to_citation()) for c in chunks],
        message=f"检索到 {len(chunks)} 条相关内容",
    )
