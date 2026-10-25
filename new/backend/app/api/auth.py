"""认证接口。"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select

from app.api.deps import ERR_NO_ROLE, ERR_TOKEN_REVOKED, CurrentUser, DbSession, get_principal
from app.core.permissions import Principal, resolve_org_ids
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
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
from app.models.org import AppUser, Organization, UserOrg
from app.models.project import Project
from app.schemas import (
    ApiResponse,
    CurrentUserOut,
    ChangePasswordIn,
    LoginRequest,
    MembershipOut,
    PasswordChangeOut,
    ProfileUpdateIn,
    OrgBrief,
    RefreshRequest,
    TokenPair,
)
from app.config import settings
from app.services.audit import write_audit

router = APIRouter(prefix="/auth", tags=["认证"])


@router.post("/login", response_model=ApiResponse[TokenPair], summary="登录")
def login(body: LoginRequest, db: DbSession, request: Request) -> ApiResponse[TokenPair]:
    """账号密码登录，返回 access + refresh token。

    登录成功与失败都会写审计日志，失败日志不记录密码。
    """
    user = db.execute(
        select(AppUser).where(AppUser.username == body.username)
    ).scalar_one_or_none()

    # 统一错误提示：不区分"用户不存在"和"密码错误"，避免账号枚举
    if user is None or not verify_password(body.password, user.password_hash):
        write_audit(
            db,
            action="LOGIN",
            target_type="app_user",
            actor_name=body.username,
            target_id=user.id if user else None,
            target_name=body.username,
            detail="登录失败：用户名或密码错误",
            request=request,
            success=False,
            commit=True,
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": 2001, "message": "用户名或密码错误"},
        )
    if not user.is_active:
        write_audit(
            db,
            action="LOGIN",
            target_type="app_user",
            actor=user,
            target_id=user.id,
            target_name=user.username,
            detail="登录失败：账号已停用",
            request=request,
            success=False,
            commit=True,
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": 2003, "message": "账号已被禁用"},
        )

    user.last_login_at = datetime.now(timezone.utc)
    write_audit(
        db,
        action="LOGIN",
        target_type="app_user",
        actor=user,
        target_id=user.id,
        target_name=user.username,
        detail="登录成功（需先修改初始密码）" if user.must_change_password else "登录成功",
        request=request,
    )
    db.commit()

    return ApiResponse(
        data=TokenPair(
            access_token=create_access_token(user.id, user.token_version),
            refresh_token=create_refresh_token(user.id, user.token_version),
            expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
            must_change_password=user.must_change_password,
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
    if int(payload.get("ver", 0)) != int(user.token_version or 0):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": ERR_TOKEN_REVOKED, "message": "登录状态已失效，请重新登录"},
        )

    return ApiResponse(
        data=TokenPair(
            access_token=create_access_token(user.id, user.token_version),
            refresh_token=create_refresh_token(user.id, user.token_version),
            expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
            must_change_password=user.must_change_password,
        )
    )


@router.patch("/me", response_model=ApiResponse[CurrentUserOut], summary="修改个人资料")
def update_me(
    body: ProfileUpdateIn,
    db: DbSession,
    user: CurrentUser,
    principal: Annotated[Principal, Depends(get_principal)],
    request: Request,
) -> ApiResponse[CurrentUserOut]:
    """用户修改自己的姓名、电话、邮箱和职称。

    姓名、职称、用户名、工号、所属单位和项目权限仍由系统管理员维护。
    """
    before = {"phone": user.phone, "email": user.email}
    for key in ("phone", "email"):
        value = getattr(body, key)
        if value is not None:
            setattr(user, key, value.strip() if isinstance(value, str) else value)
    write_audit(
        db,
        action="UPDATE",
        target_type="app_user",
        actor=user,
        target_id=user.id,
        target_name=user.name,
        before=before,
        after={"phone": user.phone, "email": user.email},
        detail="员工修改个人联系方式",
        request=request,
    )
    db.commit()
    db.refresh(user)
    return me(db=db, user=user, principal=principal)


@router.post(
    "/change-password",
    response_model=ApiResponse[PasswordChangeOut],
    summary="修改登录密码",
)
def change_password(
    body: ChangePasswordIn,
    db: DbSession,
    user: CurrentUser,
    request: Request,
) -> ApiResponse[PasswordChangeOut]:
    if not verify_password(body.old_password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": 2004, "message": "原密码不正确"},
        )
    if body.old_password == body.new_password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": 2005, "message": "新密码不能与原密码相同"},
        )
    before_version = int(user.token_version or 0)
    before_must_change = bool(user.must_change_password)
    user.password_hash = hash_password(body.new_password)
    # 递增版本：其他设备上的旧 access/refresh token 立即失效。
    user.token_version = before_version + 1
    user.must_change_password = False
    user.last_password_changed_at = datetime.now(timezone.utc)
    write_audit(
        db,
        action="UPDATE",
        target_type="app_user",
        actor=user,
        target_id=user.id,
        target_name=user.name,
        before={
            "token_version": before_version,
            "must_change_password": before_must_change,
        },
        after={
            "token_version": user.token_version,
            "must_change_password": False,
            "last_password_changed_at": user.last_password_changed_at.isoformat(),
        },
        detail="员工修改自己的登录密码，其他会话已失效",
        request=request,
    )
    db.commit()
    return ApiResponse(
        data=PasswordChangeOut(
            message="密码修改成功，其他设备已退出登录",
            access_token=create_access_token(user.id, user.token_version),
            refresh_token=create_refresh_token(user.id, user.token_version),
            expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
            must_change_password=False,
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
    links = db.execute(
        select(UserOrg, Organization)
        .join(Organization, Organization.id == UserOrg.org_id)
        .where(UserOrg.user_id == user.id)
        .order_by(UserOrg.is_primary.desc(), UserOrg.sort)
    ).all()
    orgs = [
        OrgBrief(
            id=org.id,
            name=org.name,
            short_name=org.short_name,
            org_type=org.org_type,
            is_internal=org.is_internal,
            is_unit_admin=link.is_unit_admin,
        )
        for link, org in links
    ]

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
            must_change_password=user.must_change_password,
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
