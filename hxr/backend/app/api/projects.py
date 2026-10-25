"""项目接口。

**关键点：列表接口自动按权限过滤（过滤发生在 SQL 层，不是拿到数据后再筛）。**
这是"AI 检索必须先过权限过滤再检索"的同一原则。
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import func, select

from app.api.deps import ERR_NO_ROLE, CurrentPrincipal, DbSession, require_project_view
from app.core.permissions import build_principal, scoped_project_query
from app.core.types import is_overdue
from app.models.enums import (
    RESPONSIBILITY_LABELS,
    RESPONSIBILITY_ORDER,
    ROLE_LABELS,
    STAGE_LABELS,
    UNIT_LABELS,
    DataScope,
    IssueStatus,
    OrgType,
    ProjectStatus,
    Responsibility,
    RoleCode,
    StageCode,
    StageStatus,
    UnitCode,
    stages_of_unit,
)
from app.models.issue import Issue
from app.models.org import Organization, UserOrg
from app.models.project import Project, ProjectMember, ProjectStage
from app.models.workflow import WorkflowTask
from app.schemas import (
    ApiResponse,
    ProjectCreateIn,
    ProjectOut,
    ProjectUpdateIn,
    StageOut,
)

router = APIRouter(prefix="/projects", tags=["项目"])


def _stage_label(code: str) -> str:
    try:
        return STAGE_LABELS[StageCode(code)]
    except (ValueError, KeyError):
        return code


def _role_label(code: str) -> str:
    try:
        return ROLE_LABELS[RoleCode(code)]
    except (ValueError, KeyError):
        return code


def _unit_label(code: str | None) -> str:
    if not code:
        return ""
    try:
        return UNIT_LABELS[UnitCode(code)]
    except (ValueError, KeyError):
        return code


def _resp_label(code: str | None) -> str:
    if not code:
        return ""
    try:
        return RESPONSIBILITY_LABELS[Responsibility(code)]
    except (ValueError, KeyError):
        return code


def _to_out(
    project: Project,
    principal,
    stages: list[ProjectStage] | None = None,
    pending: int = 0,
    overdue: int = 0,
    open_issues: int = 0,
) -> ProjectOut:
    # 我在本项目可能有多重参与身份（同一个人代表两个单位），
    # 展示时取"责任最重"的那个单位；完整身份列表在 /auth/me 里。
    ms = principal.memberships_in(project.id)
    unit = None
    if ms:
        unit = max(
            ms,
            key=lambda mm: RESPONSIBILITY_ORDER[
                mm.responsibility_for_display() or Responsibility.PARTICIPANT
            ],
        ).unit_code
    # 展示用责任等级：取**上面选出的那个单位**在它所有参与阶段里最重的一级。
    #
    # 这里曾经写成 responsibility_in_stage(project.id, None) —— 传 None 当阶段
    # 永远匹配不到任何阶段，于是项目卡片上"责任等级"一直是空的，
    # 而同一个单位在参与单位表里却显示"主要责任"，两处自相矛盾。
    # 根因是没意识到 responsibility_in_stage 需要具体阶段码。
    unit_map = stages_of_unit(unit) if unit else {}
    resp: Responsibility | None = None
    for r in unit_map.values():
        if resp is None or RESPONSIBILITY_ORDER[r] > RESPONSIBILITY_ORDER[resp]:
            resp = r

    my_stages = principal.visible_stages(project.id)
    my_primary = {
        st for st in StageCode if principal.is_primary_of(project.id, st.value)
    }
    return ProjectOut(
        id=project.id,
        project_no=project.project_no,
        name=project.name,
        short_name=project.short_name,
        location=project.location,
        province=project.province,
        city=project.city,
        project_type=project.project_type,
        scale_desc=project.scale_desc,
        current_stage_code=project.current_stage_code,
        current_stage_label=_stage_label(project.current_stage_code),
        status=project.status,
        plan_start=project.plan_start,
        plan_end=project.plan_end,
        actual_start=project.actual_start,
        actual_end=project.actual_end,
        my_unit=unit,
        my_unit_label=_unit_label(unit),
        my_responsibility=resp.value if resp else None,
        my_responsibility_label=_resp_label(resp.value) if resp else None,
        my_stages=sorted(s.value for s in my_stages),
        my_primary_stages=sorted(s.value for s in my_primary),
        pending_task_count=pending,
        overdue_count=overdue,
        open_issue_count=open_issues,
        stages=[
            StageOut(
                id=s.id,
                stage_code=s.stage_code,
                stage_label=_stage_label(s.stage_code),
                status=s.status,
                progress=s.progress,
                sort=s.sort,
                plan_start=s.plan_start,
                plan_end=s.plan_end,
                actual_start=s.actual_start,
                actual_end=s.actual_end,
                owner_user_id=s.owner_user_id,
            )
            for s in (stages or [])
        ],
    )


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


def _next_project_no(db: DbSession) -> str:
    """生成 ZJ-年份-三位序号，避免用户看见 UUID 式项目编号。"""
    prefix = f"ZJ-{date.today().year}-"
    rows = db.execute(select(Project.project_no).where(Project.project_no.like(f"{prefix}%"))).scalars().all()
    used: set[int] = set()
    for value in rows:
        try:
            used.add(int(str(value).rsplit("-", 1)[-1]))
        except (TypeError, ValueError):
            continue
    n = 1
    while n in used:
        n += 1
    return f"{prefix}{n:03d}"


def _creator_context(db: DbSession, principal):
    """取当前用户的主单位，并映射成权限矩阵使用的参与单位码。"""
    user_org = db.execute(
        select(UserOrg)
        .where(UserOrg.user_id == principal.user_id)
        .order_by(UserOrg.is_primary.desc(), UserOrg.sort)
    ).scalars().first()
    org = db.get(Organization, user_org.org_id) if user_org else None
    unit_code = ORG_TYPE_TO_UNIT.get(org.org_type, UnitCode.ADMIN.value) if org else UnitCode.ADMIN.value
    return org, unit_code


def _ensure_project_admin(project: Project, principal) -> None:
    if principal.is_superuser or project.created_by == principal.user_id:
        return
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail={"code": ERR_NO_ROLE, "message": "只有项目创建人或系统管理员可以修改项目信息"},
    )


@router.post("", response_model=ApiResponse[ProjectOut], summary="新建项目", status_code=201)
def create_project(
    body: ProjectCreateIn,
    db: DbSession,
    principal: CurrentPrincipal,
) -> ApiResponse[ProjectOut]:
    """从工作台新建项目，并一次性建立 7 个阶段实例。

    这是 hxr 版工作台「新建项目」能力与 oyx 版权限/阶段体系的接点。
    创建人会自动成为本项目的主单位成员，因此能立即进入项目阶段页。
    """
    org, unit_code = _creator_context(db, principal)
    project = Project(
        project_no=_next_project_no(db),
        name=body.name.strip(),
        short_name=(body.short_name or body.name).strip()[:64],
        location=body.location,
        province=body.province,
        city=body.city,
        owner_org_id=org.id if org and unit_code == UnitCode.OWNER.value else None,
        main_design_org_id=org.id if org and unit_code == UnitCode.DESIGNER.value else None,
        project_type=body.project_type or "桩基工程",
        scale_desc=body.scale_desc,
        description=body.description,
        current_stage_code=StageCode.PRE_SURVEY.value,
        status=ProjectStatus.IN_PROGRESS.value,
        created_by=principal.user_id,
    )
    db.add(project)
    db.flush()

    stages: list[ProjectStage] = []
    for idx, stage_code in enumerate(StageCode, start=1):
        ps = ProjectStage(
            project_id=project.id,
            stage_code=stage_code.value,
            status=(StageStatus.IN_PROGRESS if idx == 1 else StageStatus.NOT_STARTED).value,
            progress=10 if idx == 1 else 0,
            sort=idx,
        )
        db.add(ps)
        stages.append(ps)

    db.add(
        ProjectMember(
            project_id=project.id,
            user_id=principal.user_id,
            org_id=org.id if org else None,
            role_code=unit_code,
            stage_scope="ALL",
            data_scope=DataScope.PROJECT.value,
            granted_by=principal.user_id,
            granted_at=datetime.now(timezone.utc),
        )
    )
    db.commit()
    db.refresh(project)
    refreshed = build_principal(db, principal.user)
    return ApiResponse(data=_to_out(project, refreshed, stages=stages))


@router.patch("/{project_id}", response_model=ApiResponse[ProjectOut], summary="修改项目信息")
def update_project(
    project_id: str,
    body: ProjectUpdateIn,
    db: DbSession,
    principal: CurrentPrincipal,
) -> ApiResponse[ProjectOut]:
    require_project_view(project_id, principal)
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail={"code": 4004, "message": "项目不存在"})
    _ensure_project_admin(project, principal)

    for key in ("name", "short_name", "location", "province", "city", "project_type", "scale_desc", "description"):
        value = getattr(body, key)
        if value is not None:
            setattr(project, key, value.strip() if isinstance(value, str) else value)
    db.commit()
    db.refresh(project)

    stages = db.execute(
        select(ProjectStage).where(ProjectStage.project_id == project_id).order_by(ProjectStage.sort)
    ).scalars().all()
    return ApiResponse(data=_to_out(project, principal, stages=stages))


@router.get("", response_model=ApiResponse[list[ProjectOut]], summary="我的项目列表")
def list_projects(
    db: DbSession,
    principal: CurrentPrincipal,
    status_filter: Annotated[str | None, Query(alias="status")] = None,
    keyword: str | None = None,
) -> ApiResponse[list[ProjectOut]]:
    """我的项目列表。

    ——因为一个人会同时参与多个项目，首页就是项目列表。**这是首页数据源。**
    数据范围由权限引擎在 SQL 层过滤，无权限的项目根本不会出现在结果里。
    """
    stmt = scoped_project_query(principal)
    if status_filter:
        stmt = stmt.where(Project.status == status_filter)
    if keyword:
        like = f"%{keyword}%"
        stmt = stmt.where(Project.name.like(like) | Project.project_no.like(like))

    projects = db.execute(stmt).scalars().all()
    if not projects:
        return ApiResponse(data=[])

    pids = [p.id for p in projects]

    # 阶段信息
    stage_rows = db.execute(
        select(ProjectStage).where(ProjectStage.project_id.in_(pids)).order_by(ProjectStage.sort)
    ).scalars().all()
    stages_by_project: dict[str, list[ProjectStage]] = {}
    for s in stage_rows:
        stages_by_project.setdefault(s.project_id, []).append(s)

    # 待办统计（未处理的任务）
    # 注意：用 is_overdue() 而不是直接比较 —— SQLite 读回的时间是 naive，
    # 直接和 utcnow() 比较会抛 TypeError。
    task_rows = db.execute(
        select(WorkflowTask.project_id, WorkflowTask.due_at).where(
            WorkflowTask.project_id.in_(pids),
            WorkflowTask.action.is_(None),
        )
    ).all()
    pending_map: dict[str, int] = {}
    overdue_map: dict[str, int] = {}
    for pid, due_at in task_rows:
        pending_map[pid] = pending_map.get(pid, 0) + 1
        if is_overdue(due_at):
            overdue_map[pid] = overdue_map.get(pid, 0) + 1

    # 未闭环问题统计
    issue_rows = db.execute(
        select(Issue.project_id, func.count(Issue.id))
        .where(Issue.project_id.in_(pids), Issue.status != IssueStatus.CLOSED)
        .group_by(Issue.project_id)
    ).all()
    issue_map = {pid: cnt for pid, cnt in issue_rows}

    return ApiResponse(
        data=[
            _to_out(
                p,
                principal,
                stages=stages_by_project.get(p.id, []),
                pending=pending_map.get(p.id, 0),
                overdue=overdue_map.get(p.id, 0),
                open_issues=issue_map.get(p.id, 0),
            )
            for p in projects
        ]
    )


@router.get("/{project_id}", response_model=ApiResponse[ProjectOut], summary="项目详情")
def get_project(project_id: str, db: DbSession, principal: CurrentPrincipal) -> ApiResponse[ProjectOut]:
    require_project_view(project_id, principal)

    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": 4004, "message": "项目不存在"},
        )

    stages = db.execute(
        select(ProjectStage).where(ProjectStage.project_id == project_id).order_by(ProjectStage.sort)
    ).scalars().all()

    return ApiResponse(data=_to_out(project, principal, stages=stages))


@router.get("/{project_id}/members", response_model=ApiResponse[list[dict]], summary="项目参与人")
def list_members(project_id: str, db: DbSession, principal: CurrentPrincipal) -> ApiResponse[list[dict]]:
    """项目参与人及其角色、阶段范围。

    这是给"权限管理"页面用的，也方便前端调试"为什么我看不到某个阶段"。
    """
    require_project_view(project_id, principal)

    rows = db.execute(
        select(ProjectMember).where(
            ProjectMember.project_id == project_id,
            ProjectMember.revoked_at.is_(None),
        )
    ).scalars().all()

    from app.models.org import AppUser  # 局部导入，避免顶层循环

    user_map = {}
    if rows:
        uids = [r.user_id for r in rows]
        for u in db.execute(select(AppUser).where(AppUser.id.in_(uids))).scalars().all():
            user_map[u.id] = u

    # 单位名（页面显示"哪家单位"而不只是编码）
    org_map = {}
    oids = {r.org_id for r in rows if r.org_id}
    if oids:
        from app.models.org import Organization

        for o in db.execute(select(Organization).where(Organization.id.in_(oids))).scalars().all():
            org_map[o.id] = o

    data = []
    for r in rows:
        u = user_map.get(r.user_id)
        # 参与单位 + 由矩阵推导出的阶段责任，一并返回 ——
        # 「参与单位管理」页面据此显示"这个单位负责哪些阶段、主责哪个"。
        unit = r.role_code
        stage_map = stages_of_unit(unit)
        primary_stages = [
            st for st, resp in stage_map.items() if resp is Responsibility.PRIMARY
        ]
        related_stages = [
            st for st, resp in stage_map.items() if resp is Responsibility.RELATED
        ]
        # 展示用责任等级 = 该单位在所有参与阶段里**最重**的那一级。
        # 不能只看"有没有主办阶段" —— 监理单位没有主办阶段但是次要责任，
        # 若返回 None，界面就分不出"次要责任"和"参与"。
        top_resp: Responsibility | None = None
        for resp in stage_map.values():
            if top_resp is None or (
                RESPONSIBILITY_ORDER[resp] > RESPONSIBILITY_ORDER[top_resp]
            ):
                top_resp = resp

        org = org_map.get(r.org_id) if r.org_id else None
        data.append(
            {
                "member_id": r.id,
                "user_id": r.user_id,
                "user_name": u.name if u else None,
                "employee_no": u.employee_no if u else None,
                "org_id": r.org_id,
                "org_name": org.name if org else None,
                "unit_code": unit,
                "unit_label": _unit_label(unit),
                "stages": sorted(stage_map.keys()),
                "primary_stages": sorted(primary_stages),
                "related_stages": sorted(related_stages),
                "responsibility": top_resp.value if top_resp else None,
                "responsibility_label": _resp_label(top_resp.value) if top_resp else None,
                "data_scope": r.data_scope,
                "valid_from": r.valid_from,
                "valid_to": r.valid_to,
            }
        )
    return ApiResponse(data=data)
