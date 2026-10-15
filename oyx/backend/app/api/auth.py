"""认证接口。"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select

from app.api.deps import ERR_NO_ROLE, CurrentUser, DbSession, get_principal
from app.core.permissions import Principal, resolve_org_ids
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    verify_password,
)
from app.models.enums import (
    RESPONSIBILITY_LABELS,
    ROLE_LABELS,
    STAGE_LABELS,
    UNIT_LABELS,
    PermissionAction,
    Responsibility,
    StageCode,
    UnitCode,
)
from app.models.org import AppUser, Organization
from app.models.project import Project
from app.schemas import (
    ApiResponse,
    CurrentUserOut,
    LoginRequest,
    MembershipOut,
    OrgBrief,
    RefreshRequest,
    TokenPair,
)
from app.config import settings

router = APIRouter(prefix="/auth", tags=["认证"])


@router.post("/login", response_model=ApiResponse[TokenPair], summary="登录")
def login(body: LoginRequest, db: DbSession) -> ApiResponse[TokenPair]:
    """账号密码登录，返回 access + refresh token。

    当前为自建账号（auth_source=LOCAL）。
    后续对接院内 LDAP/AD 时，只需在 verify 环节增加分支，
    接口契约不变，前端无需改动。
    """
    user = db.execute(
        select(AppUser).where(AppUser.username == body.username)
    ).scalar_one_or_none()

    # 统一错误提示：不区分"用户不存在"和"密码错误"，避免账号枚举
    if user is None or not verify_password(body.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": 2001, "message": "用户名或密码错误"},
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": 2003, "message": "账号已被禁用"},
        )

    user.last_login_at = datetime.now(timezone.utc)
    db.commit()

    return ApiResponse(
        data=TokenPair(
            access_token=create_access_token(user.id),
            refresh_token=create_refresh_token(user.id),
            expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        )
    )


@router.post("/refresh", response_model=ApiResponse[TokenPair], summary="刷新 token")
def refresh(body: RefreshRequest, db: DbSession) -> ApiResponse[TokenPair]:
    try:
        payload = decode_token(body.refresh_token)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": 2001, "message": f"refresh token 无效：{exc}"},
        ) from exc

    if payload.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": 2001, "message": "token 类型错误，需要 refresh token"},
        )

    user = db.get(AppUser, payload.get("sub"))
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": 2001, "message": "用户不存在或已禁用"},
        )

    return ApiResponse(
        data=TokenPair(
            access_token=create_access_token(user.id),
            refresh_token=create_refresh_token(user.id),
            expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        )
    )


@router.get("/me", response_model=ApiResponse[CurrentUserOut], summary="当前用户与权限范围")
def me(
    db: DbSession,
    user: CurrentUser,
    principal: Annotated[Principal, Depends(get_principal)],
) -> ApiResponse[CurrentUserOut]:
    """返回当前用户信息 + 所属单位 + **在每个项目上的角色与权限范围**。

    前端用它决定显示哪些菜单。
    注意：这只是体验优化；真正的拦截在后端每个接口上。
    """
    org_ids = resolve_org_ids(db, user.id)
    orgs: list[OrgBrief] = []
    if org_ids:
        rows = db.execute(select(Organization).where(Organization.id.in_(org_ids))).scalars().all()
        orgs = [OrgBrief.model_validate(o) for o in rows]

    # 组装成员关系（带项目名，便于前端展示"我在哪些项目里以什么单位参与"）
    memberships: list[MembershipOut] = []
    if principal.memberships:
        pids = [m.project_id for m in principal.memberships]
        projects = {
            p.id: p.name
            for p in db.execute(select(Project).where(Project.id.in_(pids))).scalars().all()
        }
        for m in principal.memberships:
            resp = m.responsibility_for_display()
            memberships.append(
                MembershipOut(
                    project_id=m.project_id,
                    project_name=projects.get(m.project_id),
                    unit_code=m.unit_code,
                    unit_label=UNIT_LABELS.get(UnitCode(m.unit_code), m.unit_code),
                    # 阶段范围由《管理流程》矩阵推导，不是单独配的
                    stages=sorted(m.stages),
                    primary_stages=sorted(
                        st
                        for st in m.stages
                        if m.responsibility_in(st) is Responsibility.PRIMARY
                    ),
                    responsibility=resp.value if resp else None,
                    responsibility_label=(
                        RESPONSIBILITY_LABELS.get(resp, "") if resp else None
                    ),
                    actions=sorted(a.value for a in m.actions_in(None)),
                )
            )

    return ApiResponse(
        data=CurrentUserOut(
            id=user.id,
            username=user.username,
            name=user.name,
            employee_no=user.employee_no,
            phone=user.phone,
            email=user.email,
            title=user.title,
            is_superuser=user.is_superuser,
            orgs=orgs,
            memberships=memberships,
        )
    )


@router.get("/stage-options", response_model=ApiResponse[list[dict]], summary="阶段选项")
def stage_options() -> ApiResponse[list[dict]]:
    """7 个阶段的标准选项（前端阶段导航条使用）。

    统一由后端下发，避免前端硬编码顺序或文案不一致。
    """
    data = [
        {"code": s.value, "label": STAGE_LABELS[s], "sort": i + 1}
        for i, s in enumerate(StageCode)
    ]
    return ApiResponse(data=data)
