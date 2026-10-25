"""统一审计日志写入。

账号、权限、登录等管理动作都通过这里留痕。审计记录与业务变更由调用方放在
同一个事务中提交；登录失败这种需要立即返回错误的场景可以传 ``commit=True``。
"""
from __future__ import annotations

from typing import Any

from fastapi import Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.ai import AuditLog
from app.models.org import AppUser, UserOrg


def _request_meta(request: Request | None) -> tuple[str | None, str | None]:
    if request is None:
        return None, None
    ip = request.client.host if request.client else None
    return ip, request.headers.get("user-agent")


def _actor_org_id(db: Session, actor: AppUser) -> str | None:
    return db.execute(
        select(UserOrg.org_id)
        .where(UserOrg.user_id == actor.id)
        .order_by(UserOrg.is_primary.desc(), UserOrg.sort)
    ).scalars().first()


def write_audit(
    db: Session,
    *,
    action: str,
    target_type: str,
    actor: AppUser | None = None,
    actor_name: str | None = None,
    target_id: str | None = None,
    target_name: str | None = None,
    project_id: str | None = None,
    stage_code: str | None = None,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
    detail: str | None = None,
    request: Request | None = None,
    success: bool = True,
    commit: bool = False,
) -> AuditLog:
    """写一条审计日志。

    ``actor`` 为空用于记录未知账号的登录失败；此时可以只传 ``actor_name``。
    """
    ip, user_agent = _request_meta(request)
    if actor is not None:
        actor_id = actor.id
        actor_name = actor.name or actor.username
        actor_org_id = _actor_org_id(db, actor)
    else:
        actor_id = None
        actor_org_id = None

    row = AuditLog(
        project_id=project_id,
        stage_code=stage_code,
        actor=actor_id,
        actor_name=actor_name,
        actor_org_id=actor_org_id,
        action=action,
        target_type=target_type,
        target_id=target_id,
        target_name=target_name,
        before=before,
        after=after,
        detail=detail,
        ip=ip,
        user_agent=user_agent,
        success=success,
    )
    db.add(row)
    if commit:
        db.commit()
    else:
        db.flush()
    return row
