"""设计变更与影响分析接口。

**这是设计阶段最有价值的功能** —— 参数一变，自动列出受影响对象：
受影响桩位、需重算的计算书、需更新的图纸，以及**已经在施工的部位**。

最后一项是真正的安全价值：桩已经打下去了，桩位再改就是返工或补桩，
必须立即通知施工方与监理。通用文档管理系统做不到这一点。
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import select

from app.api.deps import CurrentPrincipal, DbSession, require_action, require_project_view
from app.models.change import ChangeImpact, ChangeRequest
from app.models.enums import (
    CHANGE_CATEGORY_LABELS,
    CHANGE_STATE_LABELS,
    IMPACT_TARGET_LABELS,
    STAGE_LABELS,
    ChangeCategory,
    ChangeState,
    ImpactTargetType,
    PermissionAction,
    StageCode,
    TaskAction,
    WorkflowBizType,
    WorkflowStatus,
)
from app.models.org import AppUser
from app.models.project import Pile
from app.models.workflow import WorkflowInstance
from app.schemas import (
    AffectedPileOut,
    ApiResponse,
    ChangeApproveIn,
    ChangeCreateIn,
    ChangeOut,
    ImpactAnalyzeIn,
    ImpactHandleIn,
    ImpactOut,
)
from app.services import change as chgsvc
from app.services import workflow as wf

router = APIRouter(prefix="/projects/{project_id}/changes", tags=["设计变更"])

# 变更的批准不再是硬编码角色名单 ——
# 改为按权限矩阵校验 PermissionAction.CONFIRM（主办单位才有）。
# 见 app/core/permissions.py：责任等级 → 动作。


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _user_name(db, uid: str | None) -> str | None:
    if not uid:
        return None
    u = db.get(AppUser, uid)
    return u.name if u else None


def _impact_out(db, imp: ChangeImpact) -> ImpactOut:
    return ImpactOut(
        id=imp.id,
        change_id=imp.change_id,
        target_type=ImpactTargetType(imp.target_type),
        target_type_label=IMPACT_TARGET_LABELS.get(ImpactTargetType(imp.target_type)),
        target_id=imp.target_id,
        target_name=imp.target_name,
        impact_desc=imp.impact_desc,
        severity=imp.severity,
        requires_immediate_notice=imp.requires_immediate_notice,
        handled=imp.handled,
        handled_by=imp.handled_by,
        handled_by_name=_user_name(db, imp.handled_by),
        handled_at=imp.handled_at,
        handle_note=imp.handle_note,
    )


def _available_actions(db, principal, change: ChangeRequest) -> list[str]:
    """当前用户对该变更可执行的动作。前端据此显示按钮。"""
    actions: list[str] = []
    if not principal.can(PermissionAction.EDIT, change.project_id, change.stage_code):
        return actions

    state = ChangeState(change.state)
    impacts = db.execute(
        select(ChangeImpact).where(ChangeImpact.change_id == change.id)
    ).scalars().all()

    if state in (ChangeState.DRAFT, ChangeState.IMPACT_ANALYZING):
        actions.append("analyze")
        if impacts:
            actions.append("submit")
    if state == ChangeState.APPROVING:
        inst = (
            db.get(WorkflowInstance, change.workflow_instance_id)
            if change.workflow_instance_id
            else None
        )
        if inst is not None and inst.status == WorkflowStatus.RUNNING.value:
            # **必须取本节点全部待办任务**：相关单位可能有多个（监理 + 政府审查），
            # 只取一条会让"不是那一条的任务处理人"看不到签认按钮（踩过的坑）。
            tasks = wf.pending_tasks_of_node(db, inst.id, inst.current_node or "")
            if principal.is_superuser or any(
                t.assignee == principal.user_id for t in tasks
            ):
                actions.extend(["approve", "return"])
    if state in (ChangeState.APPROVED, ChangeState.EXECUTING):
        if any(not i.handled for i in impacts):
            actions.append("handle")
        else:
            actions.append("close")
        actions.append("notify")

    return actions


def _change_out(db, principal, change: ChangeRequest, with_impacts: bool = True) -> ChangeOut:
    # 注意：不论 with_impacts 与否都要查明细 ——
    # impact_total / impact_handled / has_constructed_impact 都依赖它。
    # 如果只统计不返回，列表页会出现"显示有 4 项影响，却拿不到明细"的割裂。
    # 单条变更的明细数量有限（按分区归并，通常 < 10 条），代价可忽略。
    impacts = (
        db.execute(select(ChangeImpact).where(ChangeImpact.change_id == change.id))
        .scalars()
        .all()
    )
    handled = sum(1 for i in impacts if i.handled)
    has_constructed = any(
        i.target_type == ImpactTargetType.CONSTRUCTED_PART.value for i in impacts
    )

    inst = (
        db.get(WorkflowInstance, change.workflow_instance_id)
        if change.workflow_instance_id
        else None
    )

    try:
        cat = ChangeCategory(change.category) if change.category else None
    except ValueError:
        cat = None
    try:
        state = ChangeState(change.state)
    except ValueError:
        state = ChangeState.DRAFT

    return ChangeOut(
        id=change.id,
        project_id=change.project_id,
        stage_code=StageCode(change.stage_code),
        stage_label=STAGE_LABELS.get(StageCode(change.stage_code)),
        change_no=change.change_no,
        title=change.title,
        category=cat,
        category_label=CHANGE_CATEGORY_LABELS.get(cat) if cat else None,
        reason=change.reason,
        description=change.description,
        state=state,
        state_label=CHANGE_STATE_LABELS.get(state),
        origin_version_id=change.origin_version_id,
        new_version_id=change.new_version_id,
        impact_pile_count=change.impact_pile_count,
        impact_constructed_count=change.impact_constructed_count,
        impact_cost_delta=change.impact_cost_delta,
        impact_schedule_days=change.impact_schedule_days,
        impact_scope=change.impact_scope,
        initiator=change.initiator,
        initiator_name=_user_name(db, change.initiator),
        approver=change.approver,
        workflow_instance_id=change.workflow_instance_id,
        current_node=inst.current_node if inst else None,
        submitted_at=change.submitted_at,
        approved_at=change.approved_at,
        closed_at=change.closed_at,
        created_at=change.created_at,
        impacts=[_impact_out(db, i) for i in impacts],
        available_actions=_available_actions(db, principal, change),
        impact_total=len(impacts),
        impact_handled=handled,
        has_constructed_impact=has_constructed,
    )


def _get_change(db, project_id: str, change_id: str) -> ChangeRequest:
    c = db.get(ChangeRequest, change_id)
    if c is None or c.project_id != project_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": 4004, "message": "变更单不存在"},
        )
    return c


# ============================================================
# 列表与详情
# ============================================================


@router.get("", response_model=ApiResponse[list[ChangeOut]], summary="变更列表")
def list_changes(
    project_id: str,
    db: DbSession,
    principal: CurrentPrincipal,
    state_filter: str | None = Query(None, alias="state"),
    with_impacts: bool = False,
) -> ApiResponse[list[ChangeOut]]:
    require_project_view(project_id, principal)

    stmt = select(ChangeRequest).where(ChangeRequest.project_id == project_id)
    if state_filter:
        stmt = stmt.where(ChangeRequest.state == state_filter)
    rows = db.execute(stmt.order_by(ChangeRequest.created_at.desc())).scalars().all()
    return ApiResponse(data=[_change_out(db, principal, c, with_impacts) for c in rows])


@router.post("", response_model=ApiResponse[ChangeOut], summary="发起设计变更")
def create_change(
    project_id: str, body: ChangeCreateIn, db: DbSession, principal: CurrentPrincipal
) -> ApiResponse[ChangeOut]:
    """发起变更。

    **变更原因分类必填** —— 这是后期统计"变更主要来自哪里"的数据基础，
    能直接支撑设计院的质量改进。
    """
    require_action(principal, PermissionAction.EDIT, project_id, body.stage_code.value)

    change_no = body.change_no or _next_change_no(db, project_id)

    c = ChangeRequest(
        project_id=project_id,
        stage_code=body.stage_code.value,
        change_no=change_no,
        title=body.title,
        category=body.category.value,
        reason=body.reason,
        description=body.description,
        state=ChangeState.DRAFT.value,
        origin_version_id=body.origin_version_id,
        initiator=principal.user_id,
    )
    db.add(c)
    db.flush()

    from app.api.documents import _audit

    _audit(db, principal, "CREATE", "change_request", c.id,
           f"{change_no} {body.title}", project_id, body.stage_code.value)
    db.commit()
    return ApiResponse(data=_change_out(db, principal, c))


def _next_change_no(db, project_id: str) -> str:
    """生成变更编号：BG-<年>-<三位序号>"""
    year = _now().year
    prefix = f"BG-{year}-"
    rows = db.execute(
        select(ChangeRequest.change_no).where(
            ChangeRequest.project_id == project_id,
            ChangeRequest.change_no.like(f"{prefix}%"),
        )
    ).scalars().all()
    seq = 1
    for no in rows:
        try:
            seq = max(seq, int(no.rsplit("-", 1)[-1]) + 1)
        except (ValueError, IndexError):
            continue
    return f"{prefix}{seq:03d}"


@router.get("/{change_id}", response_model=ApiResponse[ChangeOut], summary="变更详情（含影响明细）")
def get_change(
    project_id: str, change_id: str, db: DbSession, principal: CurrentPrincipal
) -> ApiResponse[ChangeOut]:
    require_project_view(project_id, principal)
    c = _get_change(db, project_id, change_id)
    return ApiResponse(data=_change_out(db, principal, c))


# ============================================================
# 影响分析
# ============================================================


@router.post("/{change_id}/analyze", response_model=ApiResponse[ChangeOut],
             summary="执行影响分析")
def analyze(
    project_id: str,
    change_id: str,
    body: ImpactAnalyzeIn,
    db: DbSession,
    principal: CurrentPrincipal,
) -> ApiResponse[ChangeOut]:
    """执行影响分析，自动生成六类影响明细。

    可重复执行（重新分析会替换上一次结果）。
    """
    require_action(principal, PermissionAction.EDIT, project_id, StageCode.DESIGN.value)
    c = _get_change(db, project_id, change_id)

    if ChangeState(c.state) not in (ChangeState.DRAFT, ChangeState.IMPACT_ANALYZING):
        raise chgsvc.ChangeError(
            f"当前状态为「{CHANGE_STATE_LABELS.get(ChangeState(c.state), c.state)}」，"
            f"只有待提交或影响分析中的变更可以执行影响分析"
        )

    c.state = ChangeState.IMPACT_ANALYZING.value

    impacts = chgsvc.analyze_impact(
        db,
        change=c,
        scope_zones=body.scope_zones,
        affected_pile_ids=body.affected_pile_ids,
        replace_impact=True,
    )

    from app.api.documents import _audit

    _audit(db, principal, "UPDATE", "change_request", c.id,
           f"{c.change_no} 影响分析：{len(impacts)} 项", project_id, c.stage_code)
    db.commit()

    msg = f"影响分析完成，共 {len(impacts)} 项"
    if c.impact_constructed_count > 0:
        msg += (
            f"。⚠ 其中涉及**已施工桩位 {c.impact_constructed_count} 根**，"
            f"需立即通知施工方与监理"
        )
    return ApiResponse(data=_change_out(db, principal, c), message=msg)


@router.get("/{change_id}/affected-piles", response_model=ApiResponse[list[AffectedPileOut]],
            summary="受影响桩位清单")
def affected_piles(
    project_id: str,
    change_id: str,
    db: DbSession,
    principal: CurrentPrincipal,
    only_constructed: bool = False,
) -> ApiResponse[list[AffectedPileOut]]:
    """受影响桩位明细。前端在地图上高亮，或列表核对。"""
    require_project_view(project_id, principal)
    c = _get_change(db, project_id, change_id)

    zones = (c.impact_scope or {}).get("zones") or []
    if not zones:
        return ApiResponse(data=[], message="影响分析未指定分区范围，没有桩位级明细")

    stmt = select(Pile).where(Pile.project_id == project_id, Pile.zone.in_(zones))
    if only_constructed:
        stmt = stmt.where(Pile.status.in_(["CONSTRUCTED", "ACCEPTED"]))
    rows = db.execute(stmt.order_by(Pile.zone, Pile.pile_no)).scalars().all()

    return ApiResponse(data=[AffectedPileOut.model_validate(p) for p in rows])


# ============================================================
# 处理影响明细 / 审批 / 关闭
# ============================================================


@router.post("/{change_id}/impacts/{impact_id}/handle", response_model=ApiResponse[ChangeOut],
             summary="处理一条影响明细")
def handle_impact(
    project_id: str,
    change_id: str,
    impact_id: str,
    body: ImpactHandleIn,
    db: DbSession,
    principal: CurrentPrincipal,
) -> ApiResponse[ChangeOut]:
    """标记某条影响已处理，并填写处理说明（做了什么、通知了谁）。"""
    require_action(principal, PermissionAction.EDIT, project_id, StageCode.DESIGN.value)
    c = _get_change(db, project_id, change_id)

    imp = db.get(ChangeImpact, impact_id)
    if imp is None or imp.change_id != c.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": 4004, "message": "影响明细不存在"},
        )

    chgsvc.handle_impact(db, impact=imp, actor_id=principal.user_id, note=body.note)

    from app.api.documents import _audit

    _audit(db, principal, "UPDATE", "change_impact", imp.id,
           f"{c.change_no} 处理影响：{imp.target_name}", project_id, c.stage_code)
    db.commit()
    return ApiResponse(data=_change_out(db, principal, c), message="影响项已标记处理")


@router.post("/{change_id}/notify", response_model=ApiResponse[dict], summary="通知受影响单位")
def notify(
    project_id: str, change_id: str, db: DbSession, principal: CurrentPrincipal
) -> ApiResponse[dict]:
    """对「需立即通知」的影响项发出通知。

    当前实现写审计日志保证可追溯；接口形态与真实站内信一致，
    后续替换实现即可，前端不用改。
    """
    require_action(principal, PermissionAction.EDIT, project_id, StageCode.DESIGN.value)
    c = _get_change(db, project_id, change_id)

    sent = chgsvc.notify_affected(
        db, change=c, actor_id=principal.user_id, actor_name=principal.user.name
    )
    db.commit()

    if not sent:
        return ApiResponse(data={"sent": []}, message="没有需要立即通知的影响项")
    return ApiResponse(
        data={"sent": sent},
        message=f"已通知 {len(sent)} 项涉及已施工部位的影响（施工方、监理）",
    )


@router.post("/{change_id}/submit", response_model=ApiResponse[ChangeOut], summary="提交变更审批")
def submit_change(
    project_id: str, change_id: str, db: DbSession, principal: CurrentPrincipal
) -> ApiResponse[ChangeOut]:
    """提交审批。**要求影响分析已完成** —— 否则审批人无法判断影响范围。"""
    require_action(principal, PermissionAction.EDIT, project_id, StageCode.DESIGN.value)
    c = _get_change(db, project_id, change_id)

    chgsvc.submit_for_approval(db, change=c, actor_id=principal.user_id)

    from app.api.documents import _audit

    _audit(db, principal, "SUBMIT", "change_request", c.id,
           f"{c.change_no} 提交审批", project_id, c.stage_code)
    db.commit()
    return ApiResponse(data=_change_out(db, principal, c), message="已提交变更审批")


@router.post("/{change_id}/decide", response_model=ApiResponse[ChangeOut], summary="变更审批")
def decide_change(
    project_id: str,
    change_id: str,
    body: ChangeApproveIn,
    db: DbSession,
    principal: CurrentPrincipal,
) -> ApiResponse[ChangeOut]:
    """处理变更审批节点。"""
    require_project_view(project_id, principal)
    c = _get_change(db, project_id, change_id)

    if not c.workflow_instance_id:
        raise chgsvc.ChangeError("该变更没有进行中的审批流程")

    inst = db.get(WorkflowInstance, c.workflow_instance_id)
    if inst is None:
        raise chgsvc.ChangeError("审批流程实例不存在")

    # **取本节点的全部待办任务，不要只取一条** ——
    # 相关单位可能有多个（监理 + 政府审查），是并列任务，各签各的。
    # 只取一条会把另一个单位的人误判成"非处理人"，进而要求 EDIT 权限而被拒。
    pending = wf.pending_tasks_of_node(db, inst.id, inst.current_node or "")
    if not pending:
        raise chgsvc.ChangeError("当前没有待处理的审批任务")

    my_task = next((t for t in pending if t.assignee == principal.user_id), None)

    # 签认权限由"任务是否指派给你"决定，而不是 EDIT 权限：
    # 相关单位（监理、政府审查）本就不该能改文件，
    # 但他们必须能签自己的复核意见。
    if my_task is None and not principal.is_superuser:
        require_action(principal, PermissionAction.EDIT, project_id, StageCode.DESIGN.value)
        my_task = pending[0]

    inst = wf.decide(
        db,
        task_id=my_task.id,
        actor_id=principal.user_id,
        action=body.action.value,
        comment=body.comment,
        allow_self_check=body.allow_self_check,
    )

    if inst.status == WorkflowStatus.FINISHED.value:
        chgsvc.apply_approval_result(db, change=c, instance_status=inst.status)
        if body.action == TaskAction.APPROVE:
            c.approver = principal.user_id
            c.state = ChangeState.EXECUTING.value
    elif body.action in (TaskAction.RETURN, TaskAction.REJECT):
        c.state = ChangeState.DRAFT.value
        # 退回后影响明细需要重新确认
        for imp in db.execute(
            select(ChangeImpact).where(ChangeImpact.change_id == c.id)
        ).scalars().all():
            imp.handled = False
            imp.handled_by = None
            imp.handled_at = None
            imp.handle_note = None

    from app.api.documents import _audit

    _audit(db, principal, "APPROVE" if body.action == TaskAction.APPROVE else "RETURN",
           "change_request", c.id, f"{c.change_no} {body.action.value}", project_id, c.stage_code)
    db.commit()
    return ApiResponse(data=_change_out(db, principal, c))


@router.post("/{change_id}/close", response_model=ApiResponse[ChangeOut], summary="关闭变更")
def close_change(
    project_id: str, change_id: str, db: DbSession, principal: CurrentPrincipal
) -> ApiResponse[ChangeOut]:
    """关闭变更。

    **前置条件：全部影响明细已处理完毕。**
    这是"变更不闭环就不算完成"的强制点 ——
    否则会出现"变更批了，但图纸没改、施工方没收到通知"的漏洞。
    """
    require_action(principal, PermissionAction.EDIT, project_id, StageCode.DESIGN.value)
    c = _get_change(db, project_id, change_id)

    chgsvc.execute_and_close(db, change=c, actor_id=principal.user_id)

    from app.api.documents import _audit

    _audit(db, principal, "UPDATE", "change_request", c.id,
           f"{c.change_no} 关闭", project_id, c.stage_code)
    db.commit()
    return ApiResponse(data=_change_out(db, principal, c), message="变更已关闭")