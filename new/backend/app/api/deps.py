"""API 依赖注入：数据库会话、当前用户、权限主体。

**权限校验在这里统一完成，业务代码不重复写。**
前端隐藏按钮只是体验，不是安全 —— 所有校验必须在后端。
"""
from __future__ import annotations

from collections.abc import Generator
from typing import Annotated

from fastapi import Depends, Header, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.core.database import get_db
from app.core.permissions import Principal, build_principal
from app.core.security import decode_token
from app.models.enums import (
    PERMISSION_ACTION_LABELS,
    RESPONSIBILITY_LABELS,
    STAGE_LABELS,
    UNIT_LABELS,
    PermissionAction,
    StageCode,
    UnitCode,
)
from app.models.org import AppUser

# ============================================================
# 错误码
# ============================================================
ERR_UNAUTHORIZED = 2001      # 未登录 / token 无效
ERR_TOKEN_EXPIRED = 2002     # token 过期
ERR_USER_DISABLED = 2003     # 账号被禁用
ERR_TOKEN_REVOKED = 2006     # token 已失效（密码重置/停用后旧会话）
ERR_PASSWORD_CHANGE_REQUIRED = 2007  # 首次登录/重置密码后必须先改密
ERR_NO_ROLE = 3001           # 无角色（不在项目成员里）
ERR_NO_DATA_SCOPE = 3002     # 有角色但无数据范围
ERR_STAGE_DENIED = 3003      # 阶段范围不允许


def get_current_user(
    db: Annotated[Session, Depends(get_db)],
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
) -> AppUser:
    """从 Authorization: Bearer <token> 解析当前用户。"""
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": ERR_UNAUTHORIZED, "message": "未提供有效的认证信息"},
        )

    token = authorization.split(" ", 1)[1].strip()
    try:
        payload = decode_token(token)
    except ValueError as exc:
        msg = str(exc)
        code = ERR_TOKEN_EXPIRED if "过期" in msg else ERR_UNAUTHORIZED
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": code, "message": msg},
        ) from exc

    if payload.get("type") != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": ERR_UNAUTHORIZED, "message": "token 类型错误，需要 access token"},
        )

    user = db.get(AppUser, payload.get("sub"))
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": ERR_UNAUTHORIZED, "message": "用户不存在"},
        )
    if int(payload.get("ver", 0)) != int(user.token_version or 0):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": ERR_TOKEN_REVOKED, "message": "登录状态已失效，请重新登录"},
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": ERR_USER_DISABLED, "message": "账号已被禁用"},
        )
    if user.must_change_password:
        allowed_paths = {
            f"{settings.API_PREFIX}/auth/me",
            f"{settings.API_PREFIX}/auth/change-password",
        }
        if request.url.path.rstrip("/") not in allowed_paths:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "code": ERR_PASSWORD_CHANGE_REQUIRED,
                    "message": "首次登录或密码被重置后，请先修改登录密码",
                },
            )
    return user


def get_principal(
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[AppUser, Depends(get_current_user)],
) -> Principal:
    """构建权限主体（含全部有效项目成员关系）。"""
    return build_principal(db, user)


CurrentUser = Annotated[AppUser, Depends(get_current_user)]
CurrentPrincipal = Annotated[Principal, Depends(get_principal)]
DbSession = Annotated[Session, Depends(get_db)]


# ============================================================
# 权限断言（在接口里直接 Depends 使用）
# ============================================================


def require_project_view(project_id: str, principal: CurrentPrincipal) -> Principal:
    """项目查看权限断言。

    注意区分"无角色"与"无数据范围"，便于前端给出不同提示。
    """
    if principal.is_superuser:
        return principal
    if principal.membership(project_id) is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": ERR_NO_ROLE, "message": "你不是该项目的参与人"},
        )
    if not principal.can_access_project(project_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": ERR_NO_DATA_SCOPE, "message": "超出你的数据范围"},
        )
    return principal


def require_action(
    principal: Principal, action: PermissionAction, project_id: str, stage_code: str | None = None
) -> None:
    """动作 + 阶段断言。

    三层一起判：参与单位 → 阶段责任 → 动作权限。
    报错信息里说清"你是什么单位、哪个阶段不行"，便于用户自己判断，
    而不是笼统回一句"无权限"（那是踩过的坑：用户不知道找谁补权限）。
    """
    if principal.is_superuser:
        return

    if not principal.can_access_project(project_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": ERR_NO_ROLE, "message": "你不是该项目的参与单位"},
        )

    units = "、".join(
        UNIT_LABELS.get(UnitCode(u), u) for u in sorted(principal.units_in(project_id))
    ) or "无"
    stage_label = STAGE_LABELS.get(StageCode(stage_code), stage_code) if stage_code else "全部阶段"

    if not principal.can(action, project_id, stage_code):
        # 区分"阶段无责任"与"责任等级不够"，提示更有用
        if stage_code and not any(
            m.covers_stage(stage_code) for m in principal.memberships_in(project_id)
        ):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "code": ERR_STAGE_DENIED,
                    "message": f"你以「{units}」参与本项目，在「{stage_label}」阶段没有责任，"
                    f"因此无权执行 {PERMISSION_ACTION_LABELS.get(action, action)}",
                },
            )
        reason = principal.responsibility_in_stage(project_id, stage_code)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": ERR_NO_DATA_SCOPE,
                "message": f"你以「{units}」参与本项目，在「{stage_label}」阶段的身份是"
                f"「{RESPONSIBILITY_LABELS.get(reason, '参与') if reason else '无'}」，"
                f"无权执行 {PERMISSION_ACTION_LABELS.get(action, action)}",
            },
        )
