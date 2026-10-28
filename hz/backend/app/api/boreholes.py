"""钻孔台账接口 —— 地质勘察阶段的阶段功能。"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from app.api.deps import CurrentPrincipal, DbSession, require_action, require_project_view
from app.models.enums import PermissionAction, StageCode
from app.models.project import Borehole
from app.schemas import ApiResponse, BoreholeCreateIn, BoreholeOut, BoreholeUpdateIn

router = APIRouter(tags=["地质勘察钻孔"])


@router.get("/projects/{project_id}/boreholes", response_model=ApiResponse[list[BoreholeOut]], summary="钻孔列表")
def list_boreholes(project_id: str, db: DbSession, principal: CurrentPrincipal) -> ApiResponse[list[BoreholeOut]]:
    require_project_view(project_id, principal)
    rows = db.execute(
        select(Borehole).where(Borehole.project_id == project_id).order_by(Borehole.borehole_no)
    ).scalars().all()
    return ApiResponse(data=[BoreholeOut.model_validate(b) for b in rows])


@router.post("/projects/{project_id}/boreholes", response_model=ApiResponse[BoreholeOut], summary="新建钻孔")
def create_borehole(
    project_id: str, body: BoreholeCreateIn, db: DbSession, principal: CurrentPrincipal
) -> ApiResponse[BoreholeOut]:
    require_action(principal, PermissionAction.EDIT, project_id, StageCode.INVESTIGATION.value)

    exists = db.execute(
        select(Borehole).where(Borehole.project_id == project_id, Borehole.borehole_no == body.borehole_no)
    ).scalar_one_or_none()
    if exists is not None:
        raise HTTPException(status_code=400, detail={"code": 3004, "message": "该孔号已存在"})

    b = Borehole(
        project_id=project_id,
        borehole_no=body.borehole_no,
        x=body.x,
        y=body.y,
        depth=body.depth,
        elevation=body.elevation,
        survey_date=body.survey_date,
        remark=body.remark,
    )
    db.add(b)
    db.commit()
    return ApiResponse(data=BoreholeOut.model_validate(b))


@router.patch("/boreholes/{borehole_id}", response_model=ApiResponse[BoreholeOut], summary="更新钻孔")
def update_borehole(
    borehole_id: str, body: BoreholeUpdateIn, db: DbSession, principal: CurrentPrincipal
) -> ApiResponse[BoreholeOut]:
    b = db.get(Borehole, borehole_id)
    if b is None:
        raise HTTPException(status_code=404, detail={"code": 4004, "message": "钻孔不存在"})

    require_action(principal, PermissionAction.EDIT, b.project_id, StageCode.INVESTIGATION.value)

    for field in ("x", "y", "depth", "elevation", "remark"):
        if getattr(body, field) is not None:
            setattr(b, field, getattr(body, field))
    if body.survey_date is not None:
        b.survey_date = body.survey_date

    db.commit()
    return ApiResponse(data=BoreholeOut.model_validate(b))


@router.delete("/boreholes/{borehole_id}", response_model=ApiResponse[dict], summary="删除钻孔")
def delete_borehole(borehole_id: str, db: DbSession, principal: CurrentPrincipal) -> ApiResponse[dict]:
    b = db.get(Borehole, borehole_id)
    if b is None:
        raise HTTPException(status_code=404, detail={"code": 4004, "message": "钻孔不存在"})

    require_action(principal, PermissionAction.EDIT, b.project_id, StageCode.INVESTIGATION.value)

    db.delete(b)
    db.commit()
    return ApiResponse(data={"ok": True, "deleted": borehole_id})
