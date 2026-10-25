"""证照台账接口 —— 前期调研阶段的阶段功能。"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from app.api.deps import CurrentPrincipal, DbSession, require_action, require_project_view
from app.models.enums import PermissionAction, StageCode
from app.models.project import License
from app.schemas import ApiResponse, LicenseCreateIn, LicenseOut, LicenseUpdateIn

router = APIRouter(tags=["前期调研证照"])


@router.get("/projects/{project_id}/licenses", response_model=ApiResponse[list[LicenseOut]], summary="证照列表")
def list_licenses(project_id: str, db: DbSession, principal: CurrentPrincipal) -> ApiResponse[list[LicenseOut]]:
    require_project_view(project_id, principal)
    rows = db.execute(
        select(License).where(License.project_id == project_id).order_by(License.issue_date, License.name)
    ).scalars().all()
    return ApiResponse(data=[LicenseOut.model_validate(l) for l in rows])


@router.post("/projects/{project_id}/licenses", response_model=ApiResponse[LicenseOut], summary="新建证照")
def create_license(
    project_id: str, body: LicenseCreateIn, db: DbSession, principal: CurrentPrincipal
) -> ApiResponse[LicenseOut]:
    require_action(principal, PermissionAction.EDIT, project_id, StageCode.PRE_SURVEY.value)

    exists = db.execute(
        select(License).where(License.project_id == project_id, License.name == body.name)
    ).scalar_one_or_none()
    if exists is not None:
        raise HTTPException(status_code=400, detail={"code": 3004, "message": "该证照已存在"})

    lic = License(
        project_id=project_id,
        name=body.name,
        license_no=body.license_no,
        authority=body.authority,
        issue_date=body.issue_date,
        valid_until=body.valid_until,
        remark=body.remark,
    )
    db.add(lic)
    db.commit()
    return ApiResponse(data=LicenseOut.model_validate(lic))


@router.patch("/licenses/{license_id}", response_model=ApiResponse[LicenseOut], summary="更新证照")
def update_license(
    license_id: str, body: LicenseUpdateIn, db: DbSession, principal: CurrentPrincipal
) -> ApiResponse[LicenseOut]:
    lic = db.get(License, license_id)
    if lic is None:
        raise HTTPException(status_code=404, detail={"code": 4004, "message": "证照不存在"})

    require_action(principal, PermissionAction.EDIT, lic.project_id, StageCode.PRE_SURVEY.value)

    for field in ("license_no", "authority", "issue_date", "valid_until", "remark"):
        if getattr(body, field) is not None:
            setattr(lic, field, getattr(body, field))

    db.commit()
    return ApiResponse(data=LicenseOut.model_validate(lic))


@router.delete("/licenses/{license_id}", response_model=ApiResponse[dict], summary="删除证照")
def delete_license(license_id: str, db: DbSession, principal: CurrentPrincipal) -> ApiResponse[dict]:
    lic = db.get(License, license_id)
    if lic is None:
        raise HTTPException(status_code=404, detail={"code": 4004, "message": "证照不存在"})

    require_action(principal, PermissionAction.EDIT, lic.project_id, StageCode.PRE_SURVEY.value)

    db.delete(lic)
    db.commit()
    return ApiResponse(data={"ok": True, "deleted": license_id})
