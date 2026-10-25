"""问题管理与闭环服务。

对应设计 PPT 第 8 页那条链路：

    问题描述 → 查询 → 分析识别 → 建议 → 执行 → 验证 → 闭环 → 知识沉淀

**这条链要有表承载，不能只做在聊天窗口里。**

三条设计要点：

1. **链路不可跳步**：必须先"分析识别"再"建议"，先"执行"再"验证"。
   跳步会让问题记录失去可追溯性 —— 而这正是设计院最在意的。

2. **闭环互锁**：没有"验证"节点就不允许闭环。
   "执行了"和"验证有效"是两件事，混在一起会让闭环变成走形式。

3. **知识沉淀**：闭环后把问题转为知识条目，供**后续项目**与 AI 检索引用。
   这是产品越用越有价值的关键 —— 也是 AI 检索层的数据来源。
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.enums import (
    ISSUE_ACTION_LABELS,
    ISSUE_ACTION_ORDER,
    ISSUE_SOURCE_LABELS,
    ISSUE_STATUS_LABELS,
    SEVERITY_LABELS,
    IssueActionType,
    IssueSource,
    IssueStatus,
    Severity,
)
from app.models.issue import Issue, IssueAction


def _now() -> datetime:
    return datetime.now(timezone.utc)


class IssueError(HTTPException):
    def __init__(self, message: str, code: int = 4002):
        super().__init__(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": code, "message": message},
        )


# ============================================================
# 查询
# ============================================================


def list_issues(
    db: Session,
    project_id: str,
    *,
    stage_code: str | None = None,
    status_filter: str | None = None,
    source: str | None = None,
    severity: str | None = None,
    only_unclosed: bool = False,
    is_knowledge: bool | None = None,
) -> list[Issue]:
    stmt = select(Issue).where(Issue.project_id == project_id)
    if stage_code:
        stmt = stmt.where(Issue.stage_code == stage_code)
    if status_filter:
        stmt = stmt.where(Issue.status == status_filter)
    if source:
        stmt = stmt.where(Issue.source == source)
    if severity:
        stmt = stmt.where(Issue.severity == severity)
    if only_unclosed:
        stmt = stmt.where(Issue.status != IssueStatus.CLOSED.value)
    if is_knowledge is not None:
        stmt = stmt.where(Issue.is_knowledge.is_(is_knowledge))

    # 高危优先，其次按提出时间
    return list(
        db.execute(
            stmt.order_by(
                Issue.status == IssueStatus.CLOSED.value,   # 未闭环的排前面
                Issue.severity != Severity.HIGH.value,      # 高危排前面
                Issue.raise_at.desc().nullslast(),
            )
        ).scalars().all()
    )


def get_issue(db: Session, issue_id: str) -> Issue:
    iss = db.get(Issue, issue_id)
    if iss is None:
        raise IssueError("问题不存在", code=4004)
    return iss


def issue_summary(db: Session, project_id: str, stage_code: str | None = None) -> dict:
    """问题统计。页面上"未闭环问题 N 项"的数据源。"""
    rows = list_issues(db, project_id, stage_code=stage_code)
    by_status: dict[str, int] = {}
    by_severity: dict[str, int] = {}
    by_source: dict[str, int] = {}
    for r in rows:
        by_status[r.status] = by_status.get(r.status, 0) + 1
        by_severity[r.severity] = by_severity.get(r.severity, 0) + 1
        by_source[r.source] = by_source.get(r.source, 0) + 1

    now = _now()
    overdue = [
        r for r in rows
        if r.status != IssueStatus.CLOSED.value
        and r.due_date is not None
        and r.due_date < now.date()
    ]

    return {
        "total": len(rows),
        "open": by_status.get(IssueStatus.OPEN.value, 0),
        "in_progress": by_status.get(IssueStatus.IN_PROGRESS.value, 0),
        "pending_verify": by_status.get(IssueStatus.PENDING_VERIFY.value, 0),
        "closed": by_status.get(IssueStatus.CLOSED.value, 0),
        "escalated": by_status.get(IssueStatus.ESCALATED.value, 0),
        "high": by_severity.get(Severity.HIGH.value, 0),
        "overdue_count": len(overdue),
        "overdue_issues": [
            {"issue_no": r.issue_no, "title": r.title, "due_date": str(r.due_date)}
            for r in overdue[:5]
        ],
        "unclosed": len(rows) - by_status.get(IssueStatus.CLOSED.value, 0),
        "knowledge_count": sum(1 for r in rows if r.is_knowledge),
        "by_status": by_status,
        "by_source": by_source,
    }


def pending_action_types(db: Session, issue: Issue) -> list[str]:
    """该问题**下一步允许**的处理动作类型。

    前端据此只显示合法的下一步按钮，避免用户点了才被拒。
    """
    actions = db.execute(
        select(IssueAction).where(IssueAction.issue_id == issue.id)
    ).scalars().all()
    done = {a.action_type for a in actions}

    if issue.status == IssueStatus.CLOSED.value:
        # 闭环后只剩知识沉淀
        return ["KNOWLEDGE"] if not issue.is_knowledge else []

    pending: list[str] = []
    for step in ISSUE_ACTION_ORDER:
        if step.value in done:
            continue
        # CLOSE 与 KNOWLEDGE 需要满足前置条件，单独判断（见 add_action）
        if step in (IssueActionType.CLOSE, IssueActionType.KNOWLEDGE):
            continue
        pending.append(step.value)
        break  # 只允许推进到下一个未完成的步骤

    # 所有前置步骤都完成后，才允许闭环
    if not pending and IssueActionType.CLOSE.value not in done:
        pending.append(IssueActionType.CLOSE.value)

    return pending


# ============================================================
# 处理动作（链路推进）
# ============================================================

# 每个动作完成后问题进入的状态
_ACTION_TO_STATUS = {
    IssueActionType.DESCRIBE: IssueStatus.OPEN,
    IssueActionType.QUERY: IssueStatus.IN_PROGRESS,
    IssueActionType.ANALYZE: IssueStatus.IN_PROGRESS,
    IssueActionType.SUGGEST: IssueStatus.IN_PROGRESS,
    IssueActionType.EXECUTE: IssueStatus.IN_PROGRESS,
    IssueActionType.VERIFY: IssueStatus.PENDING_VERIFY,
    IssueActionType.CLOSE: IssueStatus.CLOSED,
    IssueActionType.KNOWLEDGE: IssueStatus.CLOSED,
}

# 校验规则：执行某些动作前，必须先完成的前置动作
_REQUIRES = {
    IssueActionType.QUERY: [IssueActionType.DESCRIBE],
    IssueActionType.ANALYZE: [IssueActionType.QUERY],
    IssueActionType.SUGGEST: [IssueActionType.ANALYZE],
    IssueActionType.EXECUTE: [IssueActionType.SUGGEST],
    IssueActionType.VERIFY: [IssueActionType.EXECUTE],
    IssueActionType.CLOSE: [IssueActionType.VERIFY],
    IssueActionType.KNOWLEDGE: [IssueActionType.CLOSE],
}


def add_action(
    db: Session,
    *,
    issue: Issue,
    action_type: str,
    content: str,
    actor_id: str,
    is_ai_generated: bool = False,
    ai_citation: str | None = None,
    attachment_version_id: str | None = None,
) -> IssueAction:
    """追加一条处理记录，并推进问题状态。

    **链路不可跳步** —— 这是保证问题记录可追溯的关键。
    """
    if not content or not content.strip():
        raise IssueError(
            f"「{ISSUE_ACTION_LABELS.get(IssueActionType(action_type), action_type)}」"
            f"必须填写内容",
            code=1001,
        )

    try:
        step = IssueActionType(action_type)
    except ValueError as exc:
        raise IssueError(f"未知的处理动作类型 {action_type}", code=1001) from exc

    if issue.status == IssueStatus.CLOSED.value and step != IssueActionType.KNOWLEDGE:
        raise IssueError(
            f"该问题已闭环，不能再添加「{ISSUE_ACTION_LABELS[step]}」记录。"
            f"如确有新情况，请新建问题而不是续写旧记录。"
        )

    existing = db.execute(
        select(IssueAction).where(IssueAction.issue_id == issue.id)
    ).scalars().all()
    done = {a.action_type for a in existing}

    # 幂等保护：同一步骤重复添加（DESCRIBE 除外，允许补充描述）
    if step.value in done and step != IssueActionType.DESCRIBE:
        raise IssueError(
            f"该问题的「{ISSUE_ACTION_LABELS[step]}」环节已记录过。"
            f"如需补充，请在已有记录下追加说明。"
        )

    # 前置条件校验
    missing = [
        ISSUE_ACTION_LABELS[req]
        for req in _REQUIRES.get(step, [])
        if req.value not in done
    ]
    if missing:
        raise IssueError(
            f"处理链路不能跳步：记录「{ISSUE_ACTION_LABELS[step]}」之前，"
            f"需要先完成「{'、'.join(missing)}」。"
        )

    # 验证与闭环必须有实质内容 —— 走形式会让闭环失去意义
    if step == IssueActionType.VERIFY and len(content.strip()) < 8:
        raise IssueError(
            "「验证」必须写清依据什么、由谁确认、结论如何。"
            "这一步是闭环的前提，「已确认」这类空话不算验证。",
            code=1001,
        )
    if step == IssueActionType.CLOSE and len(content.strip()) < 4:
        raise IssueError("闭环结论不能为空", code=1001)

    seq = len(existing)
    act = IssueAction(
        issue_id=issue.id,
        project_id=issue.project_id,
        action_type=step.value,
        content=content.strip(),
        is_ai_generated=is_ai_generated,
        ai_citation=ai_citation,
        actor=actor_id,
        acted_at=_now(),
        attachment_version_id=attachment_version_id,
        sort=seq + 1,
    )
    db.add(act)

    # 推进状态
    issue.status = _ACTION_TO_STATUS.get(step, issue.status).value

    if step == IssueActionType.VERIFY:
        issue.verified_by = actor_id
        issue.verified_at = _now()
        issue.verify_conclusion = content.strip()

    if step == IssueActionType.CLOSE:
        issue.closed_at = _now()
        issue.closed_by = actor_id
        # 闭环时把问题描述 + 验证结论拼成知识摘要，便于后续检索
        issue.knowledge_summary = _build_knowledge_summary(db, issue, content.strip())

    db.flush()
    return act


def _build_knowledge_summary(db: Session, issue: Issue, close_note: str) -> str:
    """生成知识摘要。

    摘要要能让**没参与过这个项目的人**看懂并复用，
    所以包含：问题 → 分析结论 → 处理办法 → 验证结果。
    """
    actions = db.execute(
        select(IssueAction)
        .where(IssueAction.issue_id == issue.id)
        .order_by(IssueAction.sort)
    ).scalars().all()
    by_type = {a.action_type: a.content for a in actions}

    parts = [f"【问题】{issue.title}"]
    if by_type.get(IssueActionType.ANALYZE.value):
        parts.append(f"【分析】{by_type[IssueActionType.ANALYZE.value]}")
    if by_type.get(IssueActionType.SUGGEST.value):
        parts.append(f"【处理办法】{by_type[IssueActionType.SUGGEST.value]}")
    if by_type.get(IssueActionType.VERIFY.value):
        parts.append(f"【验证结果】{by_type[IssueActionType.VERIFY.value]}")
    parts.append(f"【闭环结论】{close_note}")
    return "\n".join(parts)


# ============================================================
# 知识沉淀（AI 检索的数据来源）
# ============================================================


def consolidate_knowledge(
    db: Session,
    *,
    issue: Issue,
    actor_id: str,
    summary: str | None = None,
) -> tuple[Issue, object]:
    """把已闭环问题沉淀为知识条目。

    生成 knowledge_chunk 记录，供 AI 检索引用。
    **project_id 为空** —— 知识应服务后续项目，而不是锁死在本项目里。
    这条与"AI 会话严格限定在当前项目"不冲突：
    会话上下文限项目，但知识库是跨项目的经验积累。
    """
    from app.models.ai import KnowledgeChunk

    if issue.status != IssueStatus.CLOSED.value:
        raise IssueError(
            "只有已闭环的问题才能沉淀为知识条目。"
            "未经验证的处理办法不该进入知识库 —— 否则会把错误经验传播到后续项目。"
        )
    if issue.is_knowledge:
        raise IssueError("该问题已经沉淀为知识条目，无需重复操作")

    text = (summary or issue.knowledge_summary or "").strip()
    if len(text) < 20:
        raise IssueError(
            "知识摘要太短，无法复用。请补充：问题现象、分析结论、处理办法、验证结果。",
            code=1001,
        )

    chunk = KnowledgeChunk(
        project_id=None,  # 跨项目共享
        source_version_id=None,
        stage_code=issue.stage_code,
        discipline="岩土",
        doc_type="问题案例",
        section_path=f"已闭环问题 {issue.issue_no or issue.id[:8]}",
        page_no=None,
        text=text,
        token_count=len(text),  # 中文字符近似 token 数，后续接入模型时重算
        chunk_index=0,
        secret_level="INTERNAL",
        embedding_model=None,
    )
    db.add(chunk)

    issue.is_knowledge = True
    issue.knowledge_summary = text
    db.flush()

    # 记一条 KNOWLEDGE 动作，让处理链路完整
    if IssueActionType.KNOWLEDGE.value not in {
        a.action_type for a in issue.actions
    }:
        db.add(
            IssueAction(
                issue_id=issue.id,
                project_id=issue.project_id,
                action_type=IssueActionType.KNOWLEDGE.value,
                content="已沉淀为知识条目，供后续项目与 AI 检索引用",
                actor=actor_id,
                acted_at=_now(),
                sort=len(issue.actions) + 1,
            )
        )
        db.flush()

    return issue, chunk


def search_knowledge(
    db: Session,
    *,
    keyword: str | None = None,
    stage_code: str | None = None,
    limit: int = 50,
) -> list[Issue]:
    """检索已沉淀的问题知识。

    当前用关键词匹配（SQLite 全文检索能力有限）。
    接入向量库后这里换成语义检索，**接口形态不变**。
    """
    stmt = select(Issue).where(Issue.is_knowledge.is_(True))
    if stage_code:
        stmt = stmt.where(Issue.stage_code == stage_code)
    if keyword:
        like = f"%{keyword}%"
        stmt = stmt.where(
            Issue.title.like(like)
            | Issue.knowledge_summary.like(like)
            | Issue.description.like(like)
        )
    return list(db.execute(stmt.order_by(Issue.closed_at.desc()).limit(limit)).scalars().all())


# ============================================================
# 展示辅助
# ============================================================


def action_out(db: Session, act: IssueAction) -> dict:
    from app.models.org import AppUser

    actor_name = None
    if act.actor:
        u = db.get(AppUser, act.actor)
        actor_name = u.name if u else None

    try:
        step = IssueActionType(act.action_type)
        step_label = ISSUE_ACTION_LABELS[step]
        step_order = ISSUE_ACTION_ORDER.index(step) + 1
    except (ValueError, IndexError):
        step_label = act.action_type
        step_order = 0

    return {
        "id": act.id,
        "action_type": act.action_type,
        "action_label": step_label,
        "sequence": step_order,
        "content": act.content,
        "is_ai_generated": act.is_ai_generated,
        "ai_citation": act.ai_citation,
        "actor": act.actor,
        "actor_name": actor_name,
        "acted_at": act.acted_at,
        "attachment_version_id": act.attachment_version_id,
        "sort": act.sort,
    }


def status_label(s: str) -> str:
    try:
        return ISSUE_STATUS_LABELS[IssueStatus(s)]
    except (ValueError, KeyError):
        return s


def severity_label(s: str) -> str:
    try:
        return SEVERITY_LABELS[Severity(s)]
    except (ValueError, KeyError):
        return s


def source_label(s: str) -> str:
    try:
        return ISSUE_SOURCE_LABELS[IssueSource(s)]
    except (ValueError, KeyError):
        return s
