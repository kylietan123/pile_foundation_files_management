"""系统 / 部门权限管理接口。

两层管理范围：

* **总管理员**（``is_superuser``）：管理全部单位、账号与项目权限，并可重置密码。
* **部门管理员**（``user_org.is_unit_admin``）：只管理本部门账号，只能把本部门员工
  加入本部门已参与的项目，并只分配《管理流程》矩阵中本部门有责任的阶段。
  部门管理员**不能**重置密码、设置其他管理员或修改阶段责任矩阵。

员工离职采用“软停用”：账号 ``is_active`` 改为 False（数据库中的 1 → 0），
同时吊销其全部有效项目成员关系；账号与历史操作记录都保留，不做物理删除。
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone

from fastapi import APIRouter, HTTPException, Query, Request, status
from sqlalchemy import func, or_, select

from app.api.deps import CurrentUser, DbSession
from app.core.security import hash_password
from app.models.enums import (
    RESPONSIBILITY_LABELS,
    STAGE_LABELS,
    UNIT_LABELS,
    DataScope,
    OrgType,
    ProjectStatus,
    Responsibility,
    StageCode,
    UnitCode,
    stages_of_unit,
)
from app.models.org import AppUser, Organization, UserOrg
from app.models.project import Project, ProjectMember
from app.services.audit import write_audit
from app.schemas import (
    AdminBulkDisableIn,
    AdminBulkDisableOut,
    AdminBulkUserCreateIn,
    AdminBulkUserCreateOut,
    AdminMembershipOut,
    AdminOptionsOut,
    AdminOrgOut,
    AdminOverviewOut,
    AdminPasswordResetIn,
    AdminPermissionAssignment,
    AdminProjectOption,
    AdminUserCreateIn,
    AdminUserOut,
    AdminUserUpdateIn,
    ApiResponse,
)

router = APIRouter(prefix="/admin", tags=["权限管理"])

ORG_TYPE_TO_UNIT: dict[str, str] = {
    OrgType.OWNER.value: UnitCode.OWNER.value,
    OrgType.SURVEY.value: UnitCode.SURVEYOR.value,
    OrgType.DESIGN_TEST_PILE.value: UnitCode.DESIGN_TEST_PILE.value,
    OrgType.DESIGN.value: UnitCode.DESIGNER.value,
    OrgType.GENERAL_CONTRACTOR.value: UnitCode.GENERAL_CONTRACTOR.value,
    OrgType.SUBCONTRACTOR.value: UnitCode.SUBCONTRACTOR.value,
    OrgType.SUPERVISION.value: UnitCode.SUPERVISOR.value,
    OrgType.ACCEPT_TEST_PILE.value: UnitCode.ACCEPT_TEST_PILE.value,
    OrgType.INSPECTION_MONITORING.value: UnitCode.INSPECTOR.value,
    OrgType.GOVERNMENT.value: UnitCode.GOVERNMENT.value,
    OrgType.PLATFORM.value: UnitCode.ADMIN.value,
}


@dataclass(frozen=True)
class AdminScope:
    """当前管理员可见 / 可操作的范围。"""

    is_superuser: bool
    orgs: tuple[Organization, ...]
    org_ids: frozenset[str]
    unit_codes: frozenset[str]


# ============================================================
# 管理范围
# ============================================================


def _require_superuser(user: AppUser) -> None:
    if not user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": 3002, "message": "只有总管理员可以执行此操作"},
        )


def _admin_scope(db: DbSession, user: AppUser) -> AdminScope:
    """总管理员看全部启用单位；部门管理员只看自己担任管理员的单位。"""
    if user.is_superuser:
        orgs = tuple(
            db.execute(
                select(Organization)
                .where(Organization.active.is_(True))
                .order_by(Organization.name)
            ).scalars().all()
        )
        return AdminScope(
            is_superuser=True,
            orgs=orgs,
            org_ids=frozenset(o.id for o in orgs),
            unit_codes=frozenset(_unit_of_org(o) for o in orgs),
        )

    rows = db.execute(
        select(UserOrg, Organization)
        .join(Organization, Organization.id == UserOrg.org_id)
        .where(
            UserOrg.user_id == user.id,
            UserOrg.is_unit_admin.is_(True),
            Organization.active.is_(True),
        )
        .order_by(Organization.name)
    ).all()
    orgs = tuple(org for _, org in rows)
    if not orgs:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": 3002, "message": "只有总管理员或部门管理员可以访问权限管理页面"},
        )
    return AdminScope(
        is_superuser=False,
        orgs=orgs,
        org_ids=frozenset(org.id for org in orgs),
        unit_codes=frozenset(_unit_of_org(org) for org in orgs),
    )


def _unit_of_org(org: Organization | None) -> str:
    if org is None:
        return UnitCode.ADMIN.value
    return ORG_TYPE_TO_UNIT.get(org.org_type, UnitCode.ADMIN.value)


def _org_out(org: Organization | None, is_unit_admin: bool = False) -> AdminOrgOut | None:
    if org is None:
        return None
    unit = _unit_of_org(org)
    return AdminOrgOut(
        id=org.id,
        name=org.name,
        short_name=org.short_name,
        org_type=org.org_type,
        unit_code=unit,
        unit_label=UNIT_LABELS.get(UnitCode(unit), unit),
        is_unit_admin=is_unit_admin,
    )


def _stage_scope_list(raw: str | None) -> list[str]:
    if not raw or raw.strip().upper() == "ALL":
        return [s.value for s in StageCode]
    return [part.strip() for part in raw.split(",") if part.strip()]


def _override_list(raw: str | None) -> list[dict]:
    if not raw:
        return []
    rows: list[dict] = []
    for item in raw.split(","):
        if "=" not in item:
            continue
        stage_code, responsibility = (part.strip() for part in item.split("=", 1))
        rows.append({"stage_code": stage_code, "responsibility": responsibility})
    return rows


def _primary_link(db: DbSession, user_id: str) -> UserOrg | None:
    return db.execute(
        select(UserOrg)
        .where(UserOrg.user_id == user_id)
        .order_by(UserOrg.is_primary.desc(), UserOrg.sort)
    ).scalars().first()


def _has_unit_admin_role(db: DbSession, user_id: str) -> bool:
    return db.execute(
        select(UserOrg.id).where(
            UserOrg.user_id == user_id,
            UserOrg.is_unit_admin.is_(True),
        )
    ).first() is not None


def _project_ids_in_scope(db: DbSession, scope: AdminScope) -> set[str]:
    if scope.is_superuser:
        return set(db.execute(select(Project.id)).scalars().all())

    org_ids = list(scope.org_ids)
    unit_codes = list(scope.unit_codes)
    ids = set(
        db.execute(
            select(ProjectMember.project_id).where(
                ProjectMember.revoked_at.is_(None),
                or_(
                    ProjectMember.org_id.in_(org_ids),
                    ProjectMember.role_code.in_(unit_codes),
                ),
            )
        ).scalars().all()
    )
    ids.update(
        db.execute(
            select(Project.id).where(Project.owner_org_id.in_(org_ids))
        ).scalars().all()
    )
    return ids


def _scope_user_subquery(scope: AdminScope):
    return select(UserOrg.user_id).where(
        UserOrg.is_primary.is_(True),
        UserOrg.org_id.in_(list(scope.org_ids)),
    )


def _assert_target_in_scope(
    db: DbSession, scope: AdminScope, target: AppUser
) -> UserOrg:
    link = _primary_link(db, target.id)
    if link is None:
        raise HTTPException(
            status_code=400,
            detail={"code": 4000, "message": "该账号没有所属单位，无法由部门管理员管理"},
        )
    if not scope.is_superuser and link.org_id not in scope.org_ids:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": 3002, "message": "只能管理本部门员工"},
        )
    return link


def _assert_can_change_employee(
    db: DbSession, scope: AdminScope, actor: AppUser, target: AppUser
) -> UserOrg:
    """校验“能否授予 / 吊销这个员工的项目权限”。"""
    link = _assert_target_in_scope(db, scope, target)
    if scope.is_superuser:
        return link
    if target.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": 3002, "message": "总管理员账号只能由总管理员管理"},
        )
    if target.id != actor.id and _has_unit_admin_role(db, target.id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": 3002, "message": "部门管理员不能修改其他管理员账号"},
        )
    return link


# ============================================================
# 序列化
# ============================================================


def _membership_out(db: DbSession, member: ProjectMember) -> AdminMembershipOut:
    project = db.get(Project, member.project_id)
    unit = member.role_code
    return AdminMembershipOut(
        id=member.id,
        project_id=member.project_id,
        project_no=project.project_no if project else None,
        project_name=project.name if project else None,
        unit_code=unit,
        unit_label=UNIT_LABELS.get(UnitCode(unit), unit),
        stage_scope=_stage_scope_list(member.stage_scope),
        responsibility_override=_override_list(member.responsibility_override),
    )


def _user_out(db: DbSession, user: AppUser) -> AdminUserOut:
    org_rows = db.execute(
        select(UserOrg, Organization)
        .join(Organization, Organization.id == UserOrg.org_id)
        .where(UserOrg.user_id == user.id)
        .order_by(UserOrg.is_primary.desc(), UserOrg.sort)
    ).all()
    members = db.execute(
        select(ProjectMember)
        .where(ProjectMember.user_id == user.id, ProjectMember.revoked_at.is_(None))
        .order_by(ProjectMember.created_at.desc())
    ).scalars().all()
    disabled_by_name = None
    if user.disabled_by:
        disabled_by_user = db.get(AppUser, user.disabled_by)
        disabled_by_name = disabled_by_user.name if disabled_by_user else None
    return AdminUserOut(
        id=user.id,
        username=user.username,
        name=user.name,
        employee_no=user.employee_no,
        phone=user.phone,
        email=user.email,
        title=user.title,
        is_active=user.is_active,
        is_superuser=user.is_superuser,
        must_change_password=bool(user.must_change_password),
        hire_date=user.hire_date,
        leave_date=user.leave_date,
        disabled_at=user.disabled_at,
        disabled_by_name=disabled_by_name,
        disable_reason=user.disable_reason,
        last_password_changed_at=user.last_password_changed_at,
        orgs=[
            x
            for x in (_org_out(org, link.is_unit_admin) for link, org in org_rows)
            if x is not None
        ],
        memberships=[_membership_out(db, m) for m in members],
        created_at=user.created_at,
    )


def _normalize_email(value: str | None) -> str | None:
    value = (value or "").strip().lower()
    return value or None


def _normalize_employee_no(value: str | None) -> str | None:
    value = (value or "").strip().upper()
    return value or None


def _iso(value) -> str | None:
    return value.isoformat() if value else None


def _find_identity_conflicts(
    db: DbSession,
    *,
    username: str | None = None,
    employee_no: str | None = None,
    email: str | None = None,
    exclude_user_id: str | None = None,
) -> list[str]:
    conditions = []
    if username:
        conditions.append(AppUser.username == username)
    if employee_no:
        conditions.append(func.upper(AppUser.employee_no) == employee_no)
    if email:
        conditions.append(func.lower(AppUser.email) == email)
    if not conditions:
        return []

    stmt = select(AppUser).where(or_(*conditions))
    if exclude_user_id:
        stmt = stmt.where(AppUser.id != exclude_user_id)
    rows = db.execute(stmt).scalars().all()
    errors: list[str] = []
    for row in rows:
        if username and row.username == username:
            errors.append("登录账号已存在")
        if employee_no and (row.employee_no or "").upper() == employee_no:
            errors.append(f"工号 {employee_no} 已存在")
        if email and (row.email or "").lower() == email:
            errors.append(f"邮箱 {email} 已存在")
    return list(dict.fromkeys(errors))


def _user_audit_state(
    db: DbSession, user: AppUser, link: UserOrg | None = None
) -> dict:
    """账号审计快照；不包含密码哈希等敏感字段。"""
    link = link or _primary_link(db, user.id)
    members = db.execute(
        select(ProjectMember)
        .where(ProjectMember.user_id == user.id, ProjectMember.revoked_at.is_(None))
        .order_by(ProjectMember.created_at)
    ).scalars().all()
    return {
        "username": user.username,
        "name": user.name,
        "employee_no": user.employee_no,
        "phone": user.phone,
        "email": user.email,
        "title": user.title,
        "is_active": user.is_active,
        "is_superuser": user.is_superuser,
        "is_unit_admin": bool(link.is_unit_admin) if link else None,
        "token_version": int(user.token_version or 0),
        "must_change_password": bool(user.must_change_password),
        "hire_date": _iso(user.hire_date),
        "leave_date": _iso(user.leave_date),
        "disabled_at": _iso(user.disabled_at),
        "disabled_by": user.disabled_by,
        "disable_reason": user.disable_reason,
        "last_password_changed_at": _iso(user.last_password_changed_at),
        "memberships": [
            {
                "project_id": m.project_id,
                "unit_code": m.role_code,
                "stage_scope": m.stage_scope,
            }
            for m in members
        ],
    }


def _membership_audit_state(member: ProjectMember) -> dict:
    return {
        "project_id": member.project_id,
        "unit_code": member.role_code,
        "stage_scope": member.stage_scope,
        "responsibility_override": member.responsibility_override,
        "data_scope": member.data_scope,
        "revoked_at": member.revoked_at.isoformat() if member.revoked_at else None,
    }


# ============================================================
# 项目权限写入
# ============================================================


def _resolve_assignment(
    db: DbSession,
    scope: AdminScope,
    org: Organization,
    body: AdminPermissionAssignment,
) -> tuple[Project, str, list[str], str | None]:
    """校验一次授权，返回 (项目, 参与单位, 阶段列表, 责任覆盖)。"""
    project = db.get(Project, body.project_id)
    if project is None:
        raise HTTPException(status_code=404, detail={"code": 4004, "message": "项目不存在"})

    unit_code = _unit_of_org(org)
    if body.unit_code is not None and body.unit_code.value != unit_code:
        raise HTTPException(
            status_code=400,
            detail={"code": 4000, "message": "参与单位必须与员工所属单位一致"},
        )

    if scope.is_superuser:
        stage_codes = (
            [s.value for s in body.stage_scope]
            if body.stage_scope
            else [s.value for s in StageCode]
        )
    else:
        if project.id not in _project_ids_in_scope(db, scope):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={"code": 3002, "message": "只能分配本部门已参与的项目"},
            )
        if (
            project.status == ProjectStatus.PREPARING.value
            and project.owner_org_id not in scope.org_ids
        ):
            raise HTTPException(
                status_code=400,
                detail={"code": 4000, "message": "项目审核通过后才能分配其他单位人员"},
            )

        allowed = set(stages_of_unit(unit_code).keys())
        stage_codes = (
            [s.value for s in body.stage_scope]
            if body.stage_scope
            else [s.value for s in StageCode if s.value in allowed]
        )
        if not set(stage_codes).issubset(allowed):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "code": 3003,
                    "message": "只能分配本部门在《管理流程》中有责任的阶段",
                },
            )
        if body.responsibility is not None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "code": 3002,
                    "message": "阶段责任由《管理流程》矩阵决定，部门管理员不能覆盖",
                },
            )

    override = None
    if body.responsibility is not None:
        override = ",".join(
            f"{code}={body.responsibility.value}" for code in stage_codes
        )
    return project, unit_code, stage_codes, override


def _upsert_assignment(
    db: DbSession,
    *,
    user: AppUser,
    org: Organization,
    actor: AppUser,
    project: Project,
    unit_code: str,
    stage_codes: list[str],
    override: str | None,
) -> ProjectMember:
    member = db.execute(
        select(ProjectMember).where(
            ProjectMember.project_id == project.id,
            ProjectMember.user_id == user.id,
            ProjectMember.role_code == unit_code,
        )
    ).scalar_one_or_none()
    if member is None:
        member = ProjectMember(
            project_id=project.id,
            user_id=user.id,
            org_id=org.id,
            role_code=unit_code,
            data_scope=DataScope.PROJECT.value,
            granted_by=actor.id,
            granted_at=datetime.now(timezone.utc),
        )
        db.add(member)
    member.stage_scope = ",".join(stage_codes)
    member.responsibility_override = override
    member.revoked_at = None
    member.granted_by = actor.id
    member.granted_at = datetime.now(timezone.utc)
    return member


def _revoke_all_memberships(db: DbSession, user_id: str) -> int:
    members = db.execute(
        select(ProjectMember).where(
            ProjectMember.user_id == user_id,
            ProjectMember.revoked_at.is_(None),
        )
    ).scalars().all()
    now = datetime.now(timezone.utc)
    for member in members:
        member.revoked_at = now
    return len(members)


# ============================================================
# 接口
# ============================================================


@router.get("/overview", response_model=ApiResponse[AdminOverviewOut], summary="管理概览")
def overview(db: DbSession, admin: CurrentUser) -> ApiResponse[AdminOverviewOut]:
    scope = _admin_scope(db, admin)

    if scope.is_superuser:
        user_filter = []
        admin_count = db.scalar(
            select(func.count()).select_from(AppUser).where(AppUser.is_superuser.is_(True))
        ) or 0
        membership_count = db.scalar(
            select(func.count())
            .select_from(ProjectMember)
            .where(ProjectMember.revoked_at.is_(None))
        ) or 0
    else:
        user_filter = [
            AppUser.is_superuser.is_(False),
            AppUser.id.in_(_scope_user_subquery(scope)),
        ]
        admin_count = db.scalar(
            select(func.count(func.distinct(UserOrg.user_id))).where(
                UserOrg.is_unit_admin.is_(True),
                UserOrg.org_id.in_(list(scope.org_ids)),
            )
        ) or 0
        membership_count = db.scalar(
            select(func.count())
            .select_from(ProjectMember)
            .where(
                ProjectMember.revoked_at.is_(None),
                or_(
                    ProjectMember.org_id.in_(list(scope.org_ids)),
                    ProjectMember.role_code.in_(list(scope.unit_codes)),
                ),
            )
        ) or 0

    project_ids = _project_ids_in_scope(db, scope)
    data = AdminOverviewOut(
        user_count=db.scalar(
            select(func.count()).select_from(AppUser).where(*user_filter)
        ) or 0,
        active_user_count=db.scalar(
            select(func.count())
            .select_from(AppUser)
            .where(*user_filter, AppUser.is_active.is_(True))
        ) or 0,
        admin_count=admin_count,
        project_count=len(project_ids),
        org_count=len(scope.orgs),
        membership_count=membership_count,
        scope="SYSTEM" if scope.is_superuser else "UNIT",
        managed_org_names=[o.name for o in scope.orgs],
    )
    return ApiResponse(data=data)


@router.get("/options", response_model=ApiResponse[AdminOptionsOut], summary="账号与权限选项")
def options(db: DbSession, admin: CurrentUser) -> ApiResponse[AdminOptionsOut]:
    scope = _admin_scope(db, admin)
    project_ids = _project_ids_in_scope(db, scope)
    projects = db.execute(
        select(Project)
        .where(Project.id.in_(list(project_ids)))
        .order_by(Project.created_at.desc())
    ).scalars().all()
    if not scope.is_superuser:
        # 待审核项目只允许建设单位管理员先行配置，其他单位等审核通过后再分配。
        projects = [
            p
            for p in projects
            if not (
                p.status == ProjectStatus.PREPARING.value
                and p.owner_org_id not in scope.org_ids
            )
        ]

    units = (
        list(UnitCode)
        if scope.is_superuser
        else [u for u in UnitCode if u.value in scope.unit_codes]
    )
    unit_stages = {
        unit.value: [
            s.value for s in StageCode if s.value in stages_of_unit(unit.value)
        ]
        for unit in units
    }
    return ApiResponse(
        data=AdminOptionsOut(
            orgs=[x for x in (_org_out(o) for o in scope.orgs) if x is not None],
            projects=[
                AdminProjectOption(
                    id=p.id,
                    project_no=p.project_no,
                    name=p.name,
                    current_stage_code=p.current_stage_code,
                    current_stage_label=STAGE_LABELS.get(
                        StageCode(p.current_stage_code), p.current_stage_code
                    ),
                )
                for p in projects
            ],
            stages=[{"code": s.value, "label": STAGE_LABELS[s]} for s in StageCode],
            units=[{"code": u.value, "label": UNIT_LABELS[u]} for u in units],
            responsibilities=[
                {"code": r.value, "label": RESPONSIBILITY_LABELS[r]}
                for r in Responsibility
            ],
            managed_org_ids=[o.id for o in scope.orgs],
            unit_stages=unit_stages,
        )
    )


@router.get("/users", response_model=ApiResponse[list[AdminUserOut]], summary="账号列表")
def list_users(
    db: DbSession,
    admin: CurrentUser,
    keyword: str | None = Query(default=None, description="姓名、账号、工号"),
) -> ApiResponse[list[AdminUserOut]]:
    scope = _admin_scope(db, admin)
    stmt = select(AppUser)
    if not scope.is_superuser:
        stmt = stmt.where(
            AppUser.is_superuser.is_(False),
            AppUser.id.in_(_scope_user_subquery(scope)),
        )
    if keyword:
        like = f"%{keyword.strip()}%"
        stmt = stmt.where(
            AppUser.username.like(like)
            | AppUser.name.like(like)
            | AppUser.employee_no.like(like)
        )
    users = db.execute(stmt.order_by(AppUser.created_at.desc())).scalars().all()
    return ApiResponse(data=[_user_out(db, u) for u in users])


@router.post(
    "/users",
    response_model=ApiResponse[AdminUserOut],
    summary="创建员工账号",
    status_code=201,
)
def create_user(
    body: AdminUserCreateIn,
    db: DbSession,
    admin: CurrentUser,
    request: Request,
) -> ApiResponse[AdminUserOut]:
    scope = _admin_scope(db, admin)
    username = body.username.strip().lower()
    employee_no = _normalize_employee_no(body.employee_no)
    email = _normalize_email(body.email)
    conflicts = _find_identity_conflicts(
        db, username=username, employee_no=employee_no, email=email
    )
    if conflicts:
        raise HTTPException(
            status_code=409,
            detail={"code": 4009, "message": "；".join(conflicts)},
        )
    org = db.get(Organization, body.org_id)
    if org is None or not org.active:
        raise HTTPException(status_code=404, detail={"code": 4004, "message": "参与单位不存在"})
    if not scope.is_superuser and org.id not in scope.org_ids:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": 3002, "message": "只能在本部门创建员工账号"},
        )
    if not scope.is_superuser and (body.is_superuser or body.is_unit_admin):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": 3002, "message": "只有总管理员可以设置系统管理员或部门管理员"},
        )

    # 先校验全部授权，避免账号创建成功但权限只写入一半。
    resolved = [
        _resolve_assignment(db, scope, org, assignment)
        for assignment in body.assignments
    ]

    user = AppUser(
        username=username,
        password_hash=hash_password(body.password),
        name=body.name.strip(),
        employee_no=employee_no,
        phone=body.phone,
        email=email,
        title=body.title,
        hire_date=body.hire_date,
        is_superuser=body.is_superuser,
        is_active=True,
        must_change_password=True,
        last_password_changed_at=datetime.now(timezone.utc),
    )
    db.add(user)
    db.flush()
    db.add(
        UserOrg(
            user_id=user.id,
            org_id=org.id,
            is_primary=True,
            is_unit_admin=body.is_unit_admin,
            title_in_org=body.title,
            start_date=body.hire_date,
        )
    )
    for project, unit_code, stage_codes, override in resolved:
        member = _upsert_assignment(
            db,
            user=user,
            org=org,
            actor=admin,
            project=project,
            unit_code=unit_code,
            stage_codes=stage_codes,
            override=override,
        )
        db.flush()
        write_audit(
            db,
            action="GRANT",
            target_type="project_member",
            actor=admin,
            target_id=member.id,
            target_name=f"{user.name} / {project.name}",
            project_id=project.id,
            after=_membership_audit_state(member),
            detail=(
                f"创建账号时分配初始项目权限；参与单位：{unit_code}；"
                f"阶段：{', '.join(stage_codes)}"
            ),
            request=request,
        )
    db.flush()
    write_audit(
        db,
        action="CREATE",
        target_type="app_user",
        actor=admin,
        target_id=user.id,
        target_name=user.name,
        after=_user_audit_state(db, user),
        detail=(
            f"创建员工账号；所属单位：{org.name}；初始项目权限：{len(resolved)} 个；"
            "首次登录必须修改初始密码"
        ),
        request=request,
    )
    db.commit()
    db.refresh(user)
    return ApiResponse(data=_user_out(db, user))


@router.post(
    "/users/bulk",
    response_model=ApiResponse[AdminBulkUserCreateOut],
    summary="批量入职",
    status_code=201,
)
def bulk_create_users(
    body: AdminBulkUserCreateIn,
    db: DbSession,
    admin: CurrentUser,
    request: Request,
) -> ApiResponse[AdminBulkUserCreateOut]:
    scope = _admin_scope(db, admin)
    org = db.get(Organization, body.org_id)
    if org is None or not org.active:
        raise HTTPException(status_code=404, detail={"code": 4004, "message": "参与单位不存在"})
    if not scope.is_superuser and org.id not in scope.org_ids:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": 3002, "message": "只能在本部门批量创建员工账号"},
        )
    resolved = [
        _resolve_assignment(db, scope, org, assignment)
        for assignment in body.assignments
    ]

    seen_usernames: set[str] = set()
    seen_employee_nos: set[str] = set()
    seen_emails: set[str] = set()
    normalized: list[tuple] = []
    errors: list[str] = []
    for idx, item in enumerate(body.users, start=1):
        username = item.username.strip().lower()
        employee_no = _normalize_employee_no(item.employee_no)
        email = _normalize_email(item.email)
        if username in seen_usernames:
            errors.append(f"第 {idx} 行登录账号在本次批量中重复")
        if employee_no and employee_no in seen_employee_nos:
            errors.append(f"第 {idx} 行工号 {employee_no} 在本次批量中重复")
        if email and email in seen_emails:
            errors.append(f"第 {idx} 行邮箱 {email} 在本次批量中重复")
        seen_usernames.add(username)
        if employee_no:
            seen_employee_nos.add(employee_no)
        if email:
            seen_emails.add(email)
        conflicts = _find_identity_conflicts(
            db, username=username, employee_no=employee_no, email=email
        )
        if conflicts:
            errors.append(f"第 {idx} 行：" + "、".join(conflicts))
        normalized.append((item, username, employee_no, email))
    if errors:
        raise HTTPException(
            status_code=409,
            detail={
                "code": 4009,
                "message": "批量入职校验失败：" + "；".join(errors[:5]),
                "errors": errors,
            },
        )

    now = datetime.now(timezone.utc)
    created: list[AppUser] = []
    for item, username, employee_no, email in normalized:
        user = AppUser(
            username=username,
            password_hash=hash_password(item.password),
            name=item.name.strip(),
            employee_no=employee_no,
            phone=item.phone,
            email=email,
            title=item.title,
            hire_date=body.hire_date,
            is_superuser=False,
            is_active=True,
            must_change_password=True,
            last_password_changed_at=now,
        )
        db.add(user)
        db.flush()
        db.add(
            UserOrg(
                user_id=user.id,
                org_id=org.id,
                is_primary=True,
                is_unit_admin=False,
                title_in_org=item.title,
                start_date=body.hire_date,
            )
        )
        for project, unit_code, stage_codes, override in resolved:
            member = _upsert_assignment(
                db,
                user=user,
                org=org,
                actor=admin,
                project=project,
                unit_code=unit_code,
                stage_codes=stage_codes,
                override=override,
            )
            db.flush()
            write_audit(
                db,
                action="GRANT",
                target_type="project_member",
                actor=admin,
                target_id=member.id,
                target_name=f"{user.name} / {project.name}",
                project_id=project.id,
                after=_membership_audit_state(member),
                detail="批量入职时分配初始项目权限",
                request=request,
            )
        db.flush()
        write_audit(
            db,
            action="CREATE",
            target_type="app_user",
            actor=admin,
            target_id=user.id,
            target_name=user.name,
            after=_user_audit_state(db, user),
            detail=f"批量入职；所属单位：{org.name}；首次登录必须修改初始密码",
            request=request,
        )
        created.append(user)

    write_audit(
        db,
        action="BULK_CREATE",
        target_type="app_user_batch",
        actor=admin,
        target_name=f"{len(created)} 名员工",
        detail=(
            f"批量入职；所属单位：{org.name}；入职日期：{body.hire_date or '未填写'}；"
            f"初始项目权限：{len(resolved)} 个"
        ),
        request=request,
    )
    db.commit()
    return ApiResponse(
        data=AdminBulkUserCreateOut(
            created_count=len(created),
            users=[_user_out(db, user) for user in created],
        )
    )


@router.patch(
    "/users/{user_id}",
    response_model=ApiResponse[AdminUserOut],
    summary="修改账号资料 / 启停账号",
)
def update_user(
    user_id: str,
    body: AdminUserUpdateIn,
    db: DbSession,
    admin: CurrentUser,
    request: Request,
) -> ApiResponse[AdminUserOut]:
    scope = _admin_scope(db, admin)
    user = db.get(AppUser, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail={"code": 4004, "message": "账号不存在"})
    link = _assert_target_in_scope(db, scope, user)

    if not scope.is_superuser:
        if body.is_unit_admin is not None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={"code": 3002, "message": "只有总管理员可以设置部门管理员"},
            )
        if user.is_superuser:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={"code": 3002, "message": "总管理员账号只能由总管理员管理"},
            )
        if user.id != admin.id and _has_unit_admin_role(db, user.id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={"code": 3002, "message": "部门管理员不能修改其他管理员账号"},
            )

    if user.id == admin.id and body.is_active is False:
        raise HTTPException(
            status_code=400,
            detail={"code": 4000, "message": "不能停用当前登录账号"},
        )

    normalized_employee_no = (
        _normalize_employee_no(body.employee_no)
        if body.employee_no is not None
        else None
    )
    normalized_email = _normalize_email(body.email) if body.email is not None else None
    if body.employee_no is not None or body.email is not None:
        conflicts = _find_identity_conflicts(
            db,
            employee_no=normalized_employee_no,
            email=normalized_email,
            exclude_user_id=user.id,
        )
        if conflicts:
            raise HTTPException(
                status_code=409,
                detail={"code": 4009, "message": "；".join(conflicts)},
            )

    before = _user_audit_state(db, user, link)
    for key in ("name", "phone", "title"):
        value = getattr(body, key)
        if value is not None:
            setattr(user, key, value)
    if body.employee_no is not None:
        user.employee_no = normalized_employee_no
    if body.email is not None:
        user.email = normalized_email
    if body.hire_date is not None:
        user.hire_date = body.hire_date
        link.start_date = body.hire_date
    if body.leave_date is not None:
        user.leave_date = body.leave_date
        if not user.is_active:
            link.end_date = body.leave_date

    revoked_count = 0
    if body.is_active is False:
        # 离职：保留账号和历史，停用账号并吊销全部有效项目权限。
        leave_date = body.leave_date or user.leave_date or date.today()
        user.is_active = False
        user.leave_date = leave_date
        user.disabled_at = datetime.now(timezone.utc)
        user.disabled_by = admin.id
        user.disable_reason = (body.disable_reason or "").strip() or "离职"
        link.end_date = leave_date
        revoked_count = _revoke_all_memberships(db, user.id)
        user.token_version = int(user.token_version or 0) + 1
    elif body.is_active is True and not before["is_active"]:
        # 重新入职/启用：清空停用信息，但旧项目权限不会自动恢复。
        user.is_active = True
        user.disabled_at = None
        user.disabled_by = None
        user.disable_reason = None
        user.leave_date = None
        link.end_date = None
    elif not user.is_active and body.disable_reason is not None:
        # 已停用账号允许管理员事后修正停用原因。
        user.disable_reason = (body.disable_reason or "").strip() or user.disable_reason

    if body.is_unit_admin is not None:
        # 走到这里只可能是总管理员（部门管理员已在上方拒绝）。
        link.is_unit_admin = body.is_unit_admin

    db.flush()
    after = _user_audit_state(db, user, link)
    if body.is_active is False:
        action = "DISABLE"
        detail = (
            f"停用账号并吊销 {revoked_count} 个项目权限；离职日期：{user.leave_date}；"
            f"原因：{user.disable_reason}；旧登录会话已失效"
        )
    elif body.is_active is True and not before["is_active"]:
        action = "ENABLE"
        detail = "启用账号；已清空停用信息；原项目权限不会自动恢复，需要重新分配"
    else:
        action = "UPDATE"
        detail = "修改员工资料/生命周期信息"
    write_audit(
        db,
        action=action,
        target_type="app_user",
        actor=admin,
        target_id=user.id,
        target_name=user.name,
        before=before,
        after=after,
        detail=detail,
        request=request,
    )

    db.commit()
    db.refresh(user)
    return ApiResponse(data=_user_out(db, user))


@router.post(
    "/users/{user_id}/reset-password",
    response_model=ApiResponse[dict],
    summary="重置密码（仅总管理员）",
)
def reset_password(
    user_id: str,
    body: AdminPasswordResetIn,
    db: DbSession,
    admin: CurrentUser,
    request: Request,
) -> ApiResponse[dict]:
    _require_superuser(admin)
    user = db.get(AppUser, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail={"code": 4004, "message": "账号不存在"})
    link = _primary_link(db, user.id)
    before = _user_audit_state(db, user, link)
    user.password_hash = hash_password(body.password)
    # 重置密码后，该账号此前签发的 access/refresh token 全部失效。
    user.token_version = int(user.token_version or 0) + 1
    user.must_change_password = True
    user.last_password_changed_at = datetime.now(timezone.utc)
    after = _user_audit_state(db, user, link)
    write_audit(
        db,
        action="RESET_PASSWORD",
        target_type="app_user",
        actor=admin,
        target_id=user.id,
        target_name=user.name,
        before=before,
        after=after,
        detail="总管理员重置密码；此前签发的登录令牌已失效",
        request=request,
    )
    db.commit()
    return ApiResponse(
        data={
            "user_id": user.id,
            "message": "密码已重置，旧会话已失效；用户下次登录必须先修改密码",
        }
    )


@router.post(
    "/users/bulk-disable",
    response_model=ApiResponse[AdminBulkDisableOut],
    summary="批量停用员工账号",
)
def bulk_disable_users(
    body: AdminBulkDisableIn,
    db: DbSession,
    admin: CurrentUser,
    request: Request,
) -> ApiResponse[AdminBulkDisableOut]:
    scope = _admin_scope(db, admin)
    user_ids = list(dict.fromkeys(body.user_ids))
    errors: list[str] = []
    targets: list[tuple[AppUser, UserOrg]] = []
    for uid in user_ids:
        user = db.get(AppUser, uid)
        if user is None:
            errors.append(f"账号 {uid} 不存在")
            continue
        link = _primary_link(db, user.id)
        if link is None:
            errors.append(f"{user.name} 没有所属单位")
            continue
        if not scope.is_superuser and link.org_id not in scope.org_ids:
            errors.append(f"{user.name} 不属于本部门")
            continue
        if user.id == admin.id:
            errors.append("不能停用当前登录账号")
            continue
        if user.is_superuser or _has_unit_admin_role(db, user.id):
            errors.append(f"{user.name} 是管理员账号，请使用单个停用操作")
            continue
        if not user.is_active:
            errors.append(f"{user.name} 已经是停用状态")
            continue
        targets.append((user, link))
    if errors:
        raise HTTPException(
            status_code=400,
            detail={
                "code": 4000,
                "message": "批量停用校验失败：" + "；".join(errors[:5]),
                "errors": errors,
            },
        )

    now = datetime.now(timezone.utc)
    leave_date = body.leave_date or date.today()
    reason = (body.disable_reason or "").strip() or "离职"
    disabled: list[AppUser] = []
    for user, link in targets:
        before = _user_audit_state(db, user, link)
        user.is_active = False
        user.leave_date = leave_date
        user.disabled_at = now
        user.disabled_by = admin.id
        user.disable_reason = reason
        user.token_version = int(user.token_version or 0) + 1
        link.end_date = leave_date
        revoked_count = _revoke_all_memberships(db, user.id)
        db.flush()
        write_audit(
            db,
            action="DISABLE",
            target_type="app_user",
            actor=admin,
            target_id=user.id,
            target_name=user.name,
            before=before,
            after=_user_audit_state(db, user, link),
            detail=(
                f"批量停用；离职日期：{leave_date}；原因：{reason}；"
                f"吊销 {revoked_count} 个项目权限；旧登录会话已失效"
            ),
            request=request,
        )
        disabled.append(user)

    write_audit(
        db,
        action="BULK_DISABLE",
        target_type="app_user_batch",
        actor=admin,
        target_name=f"{len(disabled)} 名员工",
        detail=f"批量停用；离职日期：{leave_date}；原因：{reason}",
        request=request,
    )
    db.commit()
    return ApiResponse(
        data=AdminBulkDisableOut(
            disabled_count=len(disabled),
            users=[_user_out(db, user) for user in disabled],
        )
    )


@router.post(
    "/users/{user_id}/permissions",
    response_model=ApiResponse[AdminUserOut],
    summary="给账号分配项目权限",
)
def assign_permission(
    user_id: str,
    body: AdminPermissionAssignment,
    db: DbSession,
    admin: CurrentUser,
    request: Request,
) -> ApiResponse[AdminUserOut]:
    scope = _admin_scope(db, admin)
    user = db.get(AppUser, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail={"code": 4004, "message": "账号不存在"})
    link = _assert_can_change_employee(db, scope, admin, user)
    if not user.is_active:
        raise HTTPException(
            status_code=400,
            detail={"code": 4000, "message": "账号已停用，不能分配项目权限；请先启用账号"},
        )
    org = db.get(Organization, link.org_id)
    if org is None:
        raise HTTPException(status_code=400, detail={"code": 4000, "message": "账号没有所属单位"})

    project, unit_code, stage_codes, override = _resolve_assignment(
        db, scope, org, body
    )
    existing = db.execute(
        select(ProjectMember).where(
            ProjectMember.project_id == project.id,
            ProjectMember.user_id == user.id,
            ProjectMember.role_code == unit_code,
        )
    ).scalar_one_or_none()
    before = _membership_audit_state(existing) if existing else None
    member = _upsert_assignment(
        db,
        user=user,
        org=org,
        actor=admin,
        project=project,
        unit_code=unit_code,
        stage_codes=stage_codes,
        override=override,
    )
    db.flush()
    write_audit(
        db,
        action="GRANT",
        target_type="project_member",
        actor=admin,
        target_id=member.id,
        target_name=f"{user.name} / {project.name}",
        project_id=project.id,
        before=before,
        after=_membership_audit_state(member),
        detail=(
            f"分配项目权限；参与单位：{unit_code}；阶段：{', '.join(stage_codes)}；"
            f"责任覆盖：{override or '按标准矩阵'}"
        ),
        request=request,
    )
    db.commit()
    return ApiResponse(data=_user_out(db, user))


@router.delete(
    "/users/{user_id}/permissions/{member_id}",
    response_model=ApiResponse[AdminUserOut],
    summary="吊销单个项目权限",
)
def revoke_permission(
    user_id: str,
    member_id: str,
    db: DbSession,
    admin: CurrentUser,
    request: Request,
) -> ApiResponse[AdminUserOut]:
    scope = _admin_scope(db, admin)
    user = db.get(AppUser, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail={"code": 4004, "message": "账号不存在"})
    _assert_can_change_employee(db, scope, admin, user)

    member = db.get(ProjectMember, member_id)
    if member is None or member.user_id != user.id:
        raise HTTPException(status_code=404, detail={"code": 4004, "message": "项目权限不存在"})
    if not scope.is_superuser and (
        member.org_id not in scope.org_ids and member.role_code not in scope.unit_codes
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": 3002, "message": "只能吊销本部门的项目权限"},
        )

    project = db.get(Project, member.project_id)
    before = _membership_audit_state(member)
    member.revoked_at = datetime.now(timezone.utc)
    db.flush()
    write_audit(
        db,
        action="REVOKE",
        target_type="project_member",
        actor=admin,
        target_id=member.id,
        target_name=f"{user.name} / {project.name if project else member.project_id}",
        project_id=member.project_id,
        before=before,
        after=_membership_audit_state(member),
        detail="取消员工项目权限；账号保留",
        request=request,
    )
    db.commit()
    return ApiResponse(data=_user_out(db, user))
