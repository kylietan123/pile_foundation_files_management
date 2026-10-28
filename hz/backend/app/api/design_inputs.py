"""设计输入接口 —— 参数溯源链的对外入口。

这是设计阶段最有辨识度的部分：
    每个参数都能点开 "来源"，看到它来自哪份勘察报告的哪个版本、第几页、哪张表，
    并且能看出**来源文件是否已有更新版本**（has_newer_published）。

锁定语义：
    必填参数全部核验通过 → 可锁定设计输入。
    锁定后任何修改都必须走设计变更（否则设计依据会被悄悄改掉）。
"""
from __future__ import annotations

from fastapi import APIRouter, status

from app.api.deps import CurrentPrincipal, DbSession, require_action, require_project_view
from app.models.enums import (
    VERIFY_STATUS_LABELS,
    STAGE_LABELS,
    PermissionAction,
    StageCode,
    VerifyStatus,
)
from app.models.org import AppUser
from app.models.project import DesignParam
from app.schemas import (
    ApiResponse,
    DesignInputSummaryOut,
    DesignParamOut,
    DesignParamVerifyIn,
    LockInputsIn,
    ParamSourceOut,
    RelinkSourceIn,
    StaleRefreshOut,
    UnlockInputsIn,
)
from app.services import design_input as disvc

router = APIRouter(prefix="/projects/{project_id}/design-inputs", tags=["设计输入"])


def _display_value(p: DesignParam) -> str:
    if p.value_num is not None:
        # 整数不显示小数点，保持工程习惯
        v = p.value_num
        s = str(int(v)) if float(v).is_integer() else f"{v:g}"
        return f"{s} {p.unit}".strip() if p.unit else s
    if p.value_text:
        return f"{p.value_text} {p.unit}".strip() if p.unit else p.value_text
    return "—"


def _out(db, principal, p: DesignParam, with_source: bool = True) -> DesignParamOut:
    names = {}
    if p.verified_by:
        u = db.get(AppUser, p.verified_by)
        names[p.verified_by] = u.name if u else ""

    src = None
    if with_source:
        info = disvc.source_info(db, p)
        src = ParamSourceOut(**info) if info else None

    return DesignParamOut(
        id=p.id,
        project_id=p.project_id,
        stage_code=StageCode(p.stage_code) if p.stage_code else None,
        param_code=p.param_code,
        param_name=p.param_name,
        param_group=p.param_group,
        value_num=p.value_num,
        value_text=p.value_text,
        unit=p.unit,
        display_value=_display_value(p),
        source_type=p.source_type,
        source_version_id=p.source_version_id,
        source_locator=p.source_locator,
        source=src,
        verify_status=VerifyStatus(p.verify_status),
        verify_status_label=VERIFY_STATUS_LABELS.get(
            VerifyStatus(p.verify_status), p.verify_status
        ),
        required=p.required,
        verified_by=p.verified_by,
        verified_by_name=names.get(p.verified_by or ""),
        verified_at=p.verified_at,
        verify_note=p.verify_note,
        locked=p.locked,
        locked_at=p.locked_at,
    )


@router.get("", response_model=ApiResponse[list[DesignParamOut]], summary="设计输入参数清单")
def list_inputs(
    project_id: str,
    db: DbSession,
    principal: CurrentPrincipal,
    group: str | None = None,
    verify_status: str | None = None,
    only_unverified: bool = False,
) -> ApiResponse[list[DesignParamOut]]:
    """三层结构参数清单：场地与地层 / 荷载与上部结构 / 边界与约束。"""
    require_project_view(project_id, principal)
    rows = disvc.list_params(
        db, project_id, group=group, verify_status=verify_status, only_unverified=only_unverified
    )
    return ApiResponse(data=[_out(db, principal, r) for r in rows])


@router.get("/summary", response_model=ApiResponse[DesignInputSummaryOut], summary="核验进度汇总")
def inputs_summary(
    project_id: str, db: DbSession, principal: CurrentPrincipal
) -> ApiResponse[DesignInputSummaryOut]:
    """核验进度。前端"设计输入核验状态"卡片与"能否锁定"判断都用它。"""
    require_project_view(project_id, principal)
    return ApiResponse(data=DesignInputSummaryOut(**disvc.param_summary(db, project_id)))


@router.get("/{param_id}", response_model=ApiResponse[DesignParamOut], summary="参数详情（含来源）")
def get_input(
    project_id: str, param_id: str, db: DbSession, principal: CurrentPrincipal
) -> ApiResponse[DesignParamOut]:
    require_project_view(project_id, principal)
    p = disvc.get_param(db, param_id)
    if p.project_id != project_id:
        from fastapi import HTTPException

        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": 4004, "message": "参数不属于该项目"},
        )
    return ApiResponse(data=_out(db, principal, p))


@router.post("/{param_id}/verify", response_model=ApiResponse[DesignParamOut], summary="核验参数")
def verify_input(
    project_id: str,
    param_id: str,
    body: DesignParamVerifyIn,
    db: DbSession,
    principal: CurrentPrincipal,
) -> ApiResponse[DesignParamOut]:
    """核验单个参数。

    action:
      verify   通过核验
      modify   修改取值后通过（保留原来源，另记人工修改，溯源链不断）
      doubtful 标记存疑（挂起，需资料提供方澄清）
      pending  撤销核验，回到待核验
    """
    require_action(principal, PermissionAction.EDIT, project_id, StageCode.DESIGN.value)
    p = disvc.get_param(db, param_id)
    if p.project_id != project_id:
        from fastapi import HTTPException

        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": 4004, "message": "参数不属于该项目"},
        )

    p = disvc.verify_param(
        db,
        param=p,
        actor_id=principal.user_id,
        action=body.action,
        new_value_num=body.new_value_num,
        new_value_text=body.new_value_text,
        note=body.note,
    )

    from app.api.documents import _audit

    _audit(db, principal, "UPDATE", "design_param", p.id,
           f"{p.param_name} {body.action}", project_id, StageCode.DESIGN.value)
    db.commit()
    return ApiResponse(data=_out(db, principal, p))


@router.post("/{param_id}/relink-source", response_model=ApiResponse[DesignParamOut],
             summary="把参数来源指向新的文件版本")
def relink_source(
    project_id: str,
    param_id: str,
    body: RelinkSourceIn,
    db: DbSession,
    principal: CurrentPrincipal,
) -> ApiResponse[DesignParamOut]:
    """当来源文件发布了新版本时，人工确认参数改为引用新版本。

    只能指向**已发布**版本 —— 未发布版本不可被引用。
    """
    require_action(principal, PermissionAction.EDIT, project_id, StageCode.DESIGN.value)
    p = disvc.get_param(db, param_id)
    p = disvc.relink_source(
        db, param=p, new_version_id=body.new_version_id, actor_id=principal.user_id
    )

    from app.api.documents import _audit

    _audit(db, principal, "UPDATE", "design_param", p.id,
           f"{p.param_name} 来源改指新版本", project_id, StageCode.DESIGN.value)
    db.commit()
    return ApiResponse(data=_out(db, principal, p))


@router.post("/lock", response_model=ApiResponse[dict], summary="锁定设计输入")
def lock_inputs(
    project_id: str, body: LockInputsIn, db: DbSession, principal: CurrentPrincipal
) -> ApiResponse[dict]:
    """锁定设计输入。

    前置条件：**全部必填参数都已核验**。
    锁定后任何参数修改都必须走设计变更流程。
    """
    require_action(principal, PermissionAction.EDIT, project_id, StageCode.DESIGN.value)
    result = disvc.lock_inputs(db, project_id=project_id, actor_id=principal.user_id)

    from app.api.documents import _audit

    _audit(db, principal, "UPDATE", "design_input", project_id,
           f"锁定设计输入（{result['locked_count']} 项）", project_id, StageCode.DESIGN.value)
    db.commit()
    return ApiResponse(data=result, message=f"已锁定 {result['locked_count']} 项设计输入")


@router.post("/unlock", response_model=ApiResponse[dict], summary="解锁设计输入（特权操作）")
def unlock_inputs(
    project_id: str, body: UnlockInputsIn, db: DbSession, principal: CurrentPrincipal
) -> ApiResponse[dict]:
    """解锁设计输入。

    **这是特权操作**：正常流程应该走设计变更。必须填写原因（应关联变更单号）。
    """
    require_action(principal, PermissionAction.EDIT, project_id, StageCode.DESIGN.value)
    result = disvc.unlock_inputs(
        db, project_id=project_id, actor_id=principal.user_id, reason=body.reason
    )

    from app.api.documents import _audit

    _audit(db, principal, "UPDATE", "design_input", project_id,
           f"解锁设计输入：{body.reason}", project_id, StageCode.DESIGN.value)
    db.commit()
    return ApiResponse(data=result, message="设计输入已解锁，请尽快重新核验")


@router.post("/refresh-stale", response_model=ApiResponse[StaleRefreshOut], summary="检查来源失效的参数")
def refresh_stale(
    project_id: str, db: DbSession, principal: CurrentPrincipal
) -> ApiResponse[StaleRefreshOut]:
    """检查哪些参数的来源文件已发布新版本，并自动置为「来源已失效」。

    对应页 2 上那条红色提示：
        "勘察报告（详勘）V2 已更新 → 设计输入参数需重新核验"
    """
    require_project_view(project_id, principal)
    result = disvc.refresh_stale(db, project_id)
    db.commit()
    return ApiResponse(data=StaleRefreshOut(**result))
