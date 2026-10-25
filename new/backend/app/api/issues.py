"""问题管理与闭环接口。

八段式处理链路：问题描述 → 查询 → 分析识别 → 建议 → 执行 → 验证 → 闭环 → 知识沉淀

两道强制关卡：
  1. **链路不可跳步** —— 必须先"分析识别"再"建议"，先"执行"再"验证"
  2. **闭环需要验证** —— "执行了"和"验证有效"是两件事，
     混在一起会让闭环变成走形式

知识沉淀把闭环问题转为跨项目知识条目，是 AI 检索层的数据来源。
"""
from __future__ import annotations

from datetime import date, datetime, timezone

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import select

from app.api.deps import CurrentPrincipal, DbSession, require_project_view
from app.models.enums import (
    ISSUE_ACTION_ORDER,
    STAGE_LABELS,
    IssueActionType,
    IssueSource,
    IssueStatus,
    Severity,
    StageCode,
)
from app.models.issue import Issue, IssueAction
from app.models.org import AppUser
from app.models.project import Project
from app.schemas import (
    ApiResponse,
    IssueActionIn,
    IssueActionOut,
    IssueCreateIn,
    IssueOut,
    IssueSummaryOut,
    KnowledgeConsolidateIn,
    KnowledgeItemOut,
)
from app.services import issue as issvc

router = APIRouter(tags=["问题管理"])

TOTAL_STEPS = len(ISSUE_ACTION_ORDER)


def _user_name(db, uid: str | None) -> str | None:
    if not uid:
        return None
    u = db.get(AppUser, uid)
    return u.name if u else None


def _completed_steps(db, issue_ids: list[str]) -> dict[str, int]:
    """批量统计每个问题已完成的环节数。

    为什么需要：列表接口为了减小响应体不返回处理记录，
    但"完成了几/8 环节"必须是对的 —— 否则列表显示 0/8、详情显示 4/8，
    用户会以为数据出错了。
    """
    if not issue_ids:
        return {}
    rows = db.execute(
        select(IssueAction.issue_id, IssueAction.action_type).where(
            IssueAction.issue_id.in_(issue_ids)
        )
    ).all()
    seen: dict[str, set[str]] = {}
    for iid, atype in rows:
        seen.setdefault(iid, set()).add(atype)

    valid = {s.value for s in ISSUE_ACTION_ORDER}
    return {iid: len(types & valid) for iid, types in seen.items()}


def _issue_out(
    db, principal, issue: Issue, with_actions: bool = True, completed: int | None = None
) -> IssueOut:
    actions = (
        db.execute(
            select(IssueAction)
            .where(IssueAction.issue_id == issue.id)
            .order_by(IssueAction.sort)
        ).scalars().all()
        if with_actions
        else []
    )

    # 处理进度：已完成几个环节
    if completed is None:
        done_types = {a.action_type for a in actions}
        completed = sum(1 for step in ISSUE_ACTION_ORDER if step.value in done_types)

    try:
        severity = Severity(issue.severity)
    except ValueError:
        severity = Severity.NORMAL
    try:
        source = IssueSource(issue.source)
    except ValueError:
        source = IssueSource.SELF
    try:
        st = IssueStatus(issue.status)
    except ValueError:
        st = IssueStatus.OPEN

    overdue = bool(
        issue.status != IssueStatus.CLOSED.value
        and issue.due_date is not None
        and issue.due_date < datetime.now(timezone.utc).date()
    )

    return IssueOut(
        id=issue.id,
        project_id=issue.project_id,
        stage_code=StageCode(issue.stage_code),
        stage_label=STAGE_LABELS.get(StageCode(issue.stage_code)),
        issue_no=issue.issue_no,
        title=issue.title,
        description=issue.description,
        source=source,
        source_label=issvc.source_label(issue.source),
        issue_type_id=issue.issue_type_id,
        issue_type_name=issue.issue_type_name,
        severity=severity,
        severity_label=issvc.severity_label(issue.severity),
        status=st,
        status_label=issvc.status_label(issue.status),
        related_pile_id=issue.related_pile_id,
        related_version_id=issue.related_version_id,
        related_change_id=issue.related_change_id,
        raise_by=issue.raise_by,
        raise_by_name=_user_name(db, issue.raise_by),
        raise_at=issue.raise_at,
        assignee=issue.assignee,
        assignee_name=_user_name(db, issue.assignee),
        due_date=issue.due_date,
        overdue=overdue,
        verified_by=issue.verified_by,
        verified_at=issue.verified_at,
        verify_conclusion=issue.verify_conclusion,
        closed_at=issue.closed_at,
        closed_by=issue.closed_by,
        is_knowledge=issue.is_knowledge,
        knowledge_summary=issue.knowledge_summary,
        actions=[IssueActionOut(**issvc.action_out(db, a)) for a in actions],
        available_actions=issvc.pending_action_types(db, issue),
        completed_steps=completed,
        total_steps=TOTAL_STEPS,
    )


def _get_issue(db, project_id: str, issue_id: str) -> Issue:
    iss = db.get(Issue, issue_id)
    if iss is None or iss.project_id != project_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": 4004, "message": "问题不存在"},
        )
    return iss


# ============================================================
# 权限说明（本模块与文件/变更模块不同）
# ============================================================
# 文件与变更的"写"操作要求 EDIT 权限（改动设计文件是高风险的）。
# 但**问题处理的参与者本来跨角色**：设计师提问题、审核人验证、
# 监理或业主也可以提出问题。如果要求 EDIT 权限，审核人就永远签不了
# 自己的验证意见 —— 而"验证"恰恰应该由**非提出人**来做才有意义。
#
# 所以本模块的写操作只要求**项目可见**，靠审计留痕保证可追溯。
# 刻意不放松的是：不能操作别的项目的问题（越权），见 _get_issue 的 project_id 校验。


@router.get("/projects/{project_id}/issues", response_model=ApiResponse[list[IssueOut]],
            summary="问题列表")
def list_issues(
    project_id: str,
    db: DbSession,
    principal: CurrentPrincipal,
    stage: str | None = None,
    status_filter: str | None = Query(None, alias="status"),
    source: str | None = None,
    severity: str | None = None,
    only_unclosed: bool = False,
) -> ApiResponse[list[IssueOut]]:
    require_project_view(project_id, principal)
    rows = issvc.list_issues(
        db,
        project_id,
        stage_code=stage,
        status_filter=status_filter,
        source=source,
        severity=severity,
        only_unclosed=only_unclosed,
    )
    # 列表页不返回处理记录，减小响应体；但环节进度要准确，用一次聚合查询算出来
    progress = _completed_steps(db, [r.id for r in rows])
    return ApiResponse(
        data=[
            _issue_out(db, principal, r, with_actions=False, completed=progress.get(r.id, 0))
            for r in rows
        ]
    )


@router.get("/projects/{project_id}/issues/summary", response_model=ApiResponse[IssueSummaryOut],
            summary="问题统计")
def issues_summary(
    project_id: str,
    db: DbSession,
    principal: CurrentPrincipal,
    stage: str | None = None,
) -> ApiResponse[IssueSummaryOut]:
    require_project_view(project_id, principal)
    return ApiResponse(data=IssueSummaryOut(**issvc.issue_summary(db, project_id, stage_code=stage)))


@router.post("/projects/{project_id}/issues", response_model=ApiResponse[IssueOut],
             summary="提出问题")
def create_issue(
    project_id: str, body: IssueCreateIn, db: DbSession, principal: CurrentPrincipal
) -> ApiResponse[IssueOut]:
    require_project_view(project_id, principal)

    issue_no = _next_issue_no(db, project_id)

    from app.models.dict import DictItem

    type_name = None
    if body.issue_type_id:
        it = db.get(DictItem, body.issue_type_id)
        type_name = it.name if it else None

    iss = Issue(
        project_id=project_id,
        stage_code=body.stage_code.value,
        issue_no=issue_no,
        title=body.title,
        description=body.description,
        source=body.source.value,
        issue_type_id=body.issue_type_id,
        issue_type_name=type_name,
        severity=body.severity.value,
        status=IssueStatus.OPEN.value,
        related_pile_id=body.related_pile_id,
        related_version_id=body.related_version_id,
        related_change_id=body.related_change_id,
        raise_by=principal.user_id,
        raise_at=datetime.now(timezone.utc),
        assignee=body.assignee or principal.user_id,
        due_date=body.due_date,
    )
    db.add(iss)
    db.flush()

    # 建问题时自动记一条"问题描述"，让链路从完整的第一步开始
    db.add(
        IssueAction(
            issue_id=iss.id,
            project_id=project_id,
            action_type=IssueActionType.DESCRIBE.value,
            content=body.description,
            actor=principal.user_id,
            acted_at=datetime.now(timezone.utc),
            sort=1,
        )
    )
    db.flush()

    from app.api.documents import _audit

    _audit(db, principal, "CREATE", "issue", iss.id, f"{issue_no} {body.title}",
           project_id, body.stage_code.value)
    db.commit()
    return ApiResponse(data=_issue_out(db, principal, iss))


def _next_issue_no(db, project_id: str) -> str:
    year = datetime.now(timezone.utc).year
    prefix = f"IS-{year}-"
    rows = db.execute(
        select(Issue.issue_no).where(
            Issue.project_id == project_id,
            Issue.issue_no.like(f"{prefix}%"),
        )
    ).scalars().all()
    seq = 1
    for no in rows:
        if not no:
            continue
        try:
            seq = max(seq, int(no.rsplit("-", 1)[-1]) + 1)
        except (ValueError, IndexError):
            continue
    return f"{prefix}{seq:03d}"


@router.get("/projects/{project_id}/issues/{issue_id}", response_model=ApiResponse[IssueOut],
            summary="问题详情（含处理链路）")
def get_issue(
    project_id: str, issue_id: str, db: DbSession, principal: CurrentPrincipal
) -> ApiResponse[IssueOut]:
    require_project_view(project_id, principal)
    iss = _get_issue(db, project_id, issue_id)
    return ApiResponse(data=_issue_out(db, principal, iss))


# ============================================================
# 处理链路推进
# ============================================================


@router.post("/projects/{project_id}/issues/{issue_id}/actions",
             response_model=ApiResponse[IssueOut], summary="追加处理记录（推进链路）")
def add_action(
    project_id: str,
    issue_id: str,
    body: IssueActionIn,
    db: DbSession,
    principal: CurrentPrincipal,
) -> ApiResponse[IssueOut]:
    """追加一条处理记录。

    **链路不可跳步**：必须先"分析识别"再"建议"，先"执行"再"验证"。
    跳步会让问题记录失去可追溯性，而这正是设计院最在意的。
    """
    require_project_view(project_id, principal)
    iss = _get_issue(db, project_id, issue_id)

    issvc.add_action(
        db,
        issue=iss,
        action_type=body.action_type.value,
        content=body.content,
        actor_id=principal.user_id,
        is_ai_generated=body.is_ai_generated,
        ai_citation=body.ai_citation,
        attachment_version_id=body.attachment_version_id,
    )

    from app.api.documents import _audit

    _audit(db, principal, "UPDATE", "issue", iss.id,
           f"{iss.issue_no} {body.action_type.value}", project_id, iss.stage_code)
    db.commit()
    return ApiResponse(data=_issue_out(db, principal, iss),
                      message=f"已记录「{body.action_type.value}」环节")


@router.post("/projects/{project_id}/issues/{issue_id}/reopen",
             response_model=ApiResponse[IssueOut], summary="重新打开已闭环问题")
def reopen_issue(
    project_id: str,
    issue_id: str,
    body: dict,
    db: DbSession,
    principal: CurrentPrincipal,
) -> ApiResponse[IssueOut]:
    """重新打开已闭环的问题。

    **这是例外路径**：正常应该新建问题而不是续写旧记录（保持记录的可追溯性）。
    只允许在验证发现"处理无效"时使用，必须填写原因。
    """
    require_project_view(project_id, principal)
    iss = _get_issue(db, project_id, issue_id)

    reason = (body or {}).get("reason", "").strip()
    if len(reason) < 6:
        raise issvc.IssueError("重新打开已闭环问题必须填写原因（不少于 6 个字）", code=1001)
    if iss.status != IssueStatus.CLOSED.value:
        raise issvc.IssueError("该问题尚未闭环，无需重新打开")

    iss.status = IssueStatus.IN_PROGRESS.value
    iss.closed_at = None
    iss.closed_by = None
    db.add(
        IssueAction(
            issue_id=iss.id,
            project_id=iss.project_id,
            action_type=IssueActionType.EXECUTE.value,
            content=f"[重新打开] {reason}",
            actor=principal.user_id,
            acted_at=datetime.now(timezone.utc),
            sort=len(iss.actions) + 1,
        )
    )
    db.flush()

    from app.api.documents import _audit

    _audit(db, principal, "UPDATE", "issue", iss.id,
           f"{iss.issue_no} 重新打开：{reason}", project_id, iss.stage_code)
    db.commit()
    return ApiResponse(data=_issue_out(db, principal, iss), message="问题已重新打开")


# ============================================================
# 知识沉淀与检索
# ============================================================


@router.post("/projects/{project_id}/issues/{issue_id}/consolidate",
             response_model=ApiResponse[IssueOut], summary="沉淀为知识条目")
def consolidate(
    project_id: str,
    issue_id: str,
    body: KnowledgeConsolidateIn,
    db: DbSession,
    principal: CurrentPrincipal,
) -> ApiResponse[IssueOut]:
    """把已闭环问题沉淀为知识条目，供后续项目与 AI 检索引用。

    **只有已闭环的问题才能沉淀** —— 未经验证的处理办法不该进入知识库，
    否则会把错误经验传播到后续项目。
    """
    require_project_view(project_id, principal)
    iss = _get_issue(db, project_id, issue_id)

    iss, _chunk = issvc.consolidate_knowledge(
        db, issue=iss, actor_id=principal.user_id, summary=body.summary
    )

    from app.api.documents import _audit

    _audit(db, principal, "UPDATE", "issue", iss.id,
           f"{iss.issue_no} 沉淀为知识条目", project_id, iss.stage_code)
    db.commit()
    return ApiResponse(data=_issue_out(db, principal, iss),
                      message="已沉淀为知识条目，可供后续项目检索")


@router.get("/projects/{project_id}/knowledge", response_model=ApiResponse[list[KnowledgeItemOut]],
            summary="本项目沉淀的知识条目")
def project_knowledge(
    project_id: str, db: DbSession, principal: CurrentPrincipal
) -> ApiResponse[list[KnowledgeItemOut]]:
    require_project_view(project_id, principal)
    rows = issvc.list_issues(db, project_id, is_knowledge=True)
    return ApiResponse(data=[_knowledge_out(db, r) for r in rows])


@router.get("/knowledge", response_model=ApiResponse[list[KnowledgeItemOut]],
            summary="全局知识库检索")
def search_knowledge(
    db: DbSession,
    principal: CurrentPrincipal,
    keyword: str | None = None,
    stage: str | None = None,
    limit: int = 50,
) -> ApiResponse[list[KnowledgeItemOut]]:
    """跨项目检索已沉淀的问题知识。

    **这是 AI 检索层的数据来源。**
    当前用关键词匹配（SQLite 全文检索能力有限）；
    接入向量库后换成语义检索，接口形态不变。
    """
    rows = issvc.search_knowledge(db, keyword=keyword, stage_code=stage, limit=limit)
    return ApiResponse(data=[_knowledge_out(db, r) for r in rows])


def _knowledge_out(db, iss: Issue) -> KnowledgeItemOut:
    proj = db.get(Project, iss.project_id)
    stage = None
    try:
        stage = StageCode(iss.stage_code)
    except ValueError:
        stage = None
    try:
        sev = Severity(iss.severity)
    except ValueError:
        sev = None

    return KnowledgeItemOut(
        issue_id=iss.id,
        issue_no=iss.issue_no,
        title=iss.title,
        stage_code=stage,
        stage_label=STAGE_LABELS.get(stage) if stage else None,
        severity=sev,
        knowledge_summary=iss.knowledge_summary,
        closed_at=iss.closed_at,
        project_id=iss.project_id,
        project_name=proj.name if proj else None,
    )
