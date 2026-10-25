"""监测点台账接口 —— 运维监测阶段的阶段功能。"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from app.api.deps import CurrentPrincipal, DbSession, require_action, require_project_view
from app.models.enums import PermissionAction, StageCode
from app.models.project import MonitoringPoint
from app.schemas import ApiResponse, MonitoringPointCreateIn, MonitoringPointOut, MonitoringPointUpdateIn

router = APIRouter(tags=["运维监测"])


@router.get("/projects/{project_id}/monitoring-points", response_model=ApiResponse[list[MonitoringPointOut]], summary="监测点列表")
def list_monitoring_points(project_id: str, db: DbSession, principal: CurrentPrincipal) -> ApiResponse[list[MonitoringPointOut]]:
    require_project_view(project_id, principal)
    rows = db.execute(
        select(MonitoringPoint).where(MonitoringPoint.project_id == project_id).order_by(MonitoringPoint.point_no)
    ).scalars().all()
    return ApiResponse(data=[MonitoringPointOut.model_validate(p) for p in rows])


@router.post("/projects/{project_id}/monitoring-points", response_model=ApiResponse[MonitoringPointOut], summary="新建监测点")
def create_monitoring_point(
    project_id: str, body: MonitoringPointCreateIn, db: DbSession, principal: CurrentPrincipal
) -> ApiResponse[MonitoringPointOut]:
    require_action(principal, PermissionAction.EDIT, project_id, StageCode.MONITORING.value)

    exists = db.execute(
        select(MonitoringPoint).where(MonitoringPoint.project_id == project_id, MonitoringPoint.point_no == body.point_no)
    ).scalar_one_or_none()
    if exists is not None:
        raise HTTPException(status_code=400, detail={"code": 3004, "message": "该点号已存在"})

    p = MonitoringPoint(
        project_id=project_id,
        point_no=body.point_no,
        monitor_item=body.monitor_item,
        threshold=body.threshold,
        latest_value=body.latest_value,
        unit=body.unit,
        last_measured_at=body.last_measured_at,
        remark=body.remark,
    )
    db.add(p)
    db.commit()
    return ApiResponse(data=MonitoringPointOut.model_validate(p))


@router.patch("/monitoring-points/{point_id}", response_model=ApiResponse[MonitoringPointOut], summary="更新监测点")
def update_monitoring_point(
    point_id: str, body: MonitoringPointUpdateIn, db: DbSession, principal: CurrentPrincipal
) -> ApiResponse[MonitoringPointOut]:
    p = db.get(MonitoringPoint, point_id)
    if p is None:
        raise HTTPException(status_code=404, detail={"code": 4004, "message": "监测点不存在"})

    require_action(principal, PermissionAction.EDIT, p.project_id, StageCode.MONITORING.value)

    for field in ("monitor_item", "threshold", "latest_value", "unit", "last_measured_at", "remark"):
        if getattr(body, field) is not None:
            setattr(p, field, getattr(body, field))

    db.commit()
    return ApiResponse(data=MonitoringPointOut.model_validate(p))


@router.delete("/monitoring-points/{point_id}", response_model=ApiResponse[dict], summary="删除监测点")
def delete_monitoring_point(point_id: str, db: DbSession, principal: CurrentPrincipal) -> ApiResponse[dict]:
    p = db.get(MonitoringPoint, point_id)
    if p is None:
        raise HTTPException(status_code=404, detail={"code": 4004, "message": "监测点不存在"})

    require_action(principal, PermissionAction.EDIT, p.project_id, StageCode.MONITORING.value)

    db.delete(p)
    db.commit()
    return ApiResponse(data={"ok": True, "deleted": point_id})
