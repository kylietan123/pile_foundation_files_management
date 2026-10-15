"""权限引擎 —— 以「参与单位 × 阶段 × 责任等级」为主体。

**核心原则：权限不是单独配的，是从《管理流程》矩阵推导出来的。**

    RESPONSIBILITY_MATRIX[阶段][单位] = 责任等级
                    ↓  推导
    责任等级 → 允许的动作

好处：
    1. 责任划分调整时只改矩阵一处，权限自动跟着变 ——
       不会出现"矩阵说监理负责、代码却拦住监理"这种自相矛盾；
    2. 不用为 11 个单位 × 7 个阶段分别配权限（那是 77 条配置）；
    3. 汇报时可以直接把矩阵打出来对照。

三层校验（任一不通过即拒绝）：
    第 1 层 单位：你是不是本项目的参与单位？
    第 2 层 阶段：这个阶段你有没有责任（矩阵里有没有你）？
    第 3 层 动作：你的责任等级允许做这个动作吗？

**单位内不区分岗位。** 单位里任何人都能上传 ——
责任通过"每一次操作都记录操作人姓名与编号"来落实，而不是靠限制权限。
这也是用户明确选择的方式：方便优先，追责靠留痕。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.models.enums import (
    RESPONSIBILITY_MATRIX,
    RESPONSIBILITY_ORDER,
    SECRET_ORDER,
    STAGE_ORDER,
    DataScope,
    PermissionAction,
    Responsibility,
    SecretLevel,
    StageCode,
    UnitCode,
    primary_unit_of_stage,
    responsibility_of,
    stages_of_unit,
)
from app.models.org import AppUser, UserOrg
from app.models.project import Project, ProjectMember

# ============================================================
# 责任等级 → 允许的动作
# ============================================================

_BASE = {PermissionAction.VIEW, PermissionAction.DOWNLOAD}

#: 各责任等级能做什么。读法是"这个等级的人，在本阶段能对文件做什么"。
RESPONSIBILITY_ACTIONS: dict[Responsibility, set[PermissionAction]] = {
    # 主要责任（主办）：本阶段文件由他们产出，所以能改能发
    Responsibility.PRIMARY: _BASE
    | {
        PermissionAction.EDIT,
        PermissionAction.SUBMIT,
        PermissionAction.PUBLISH,
        PermissionAction.CONFIRM,
    },
    # 次要责任（相关）：能复核提意见，但不改别人的文件
    Responsibility.RELATED: _BASE
    | {PermissionAction.CONFIRM, PermissionAction.COMMENT},
    # 参与：只能看和拿走
    Responsibility.PARTICIPANT: set(_BASE),
    # 审查（政府）：只读 + 写审查意见，不签认
    Responsibility.VERIFIER: _BASE | {PermissionAction.COMMENT},
}


def actions_of(resp: Responsibility | None) -> set[PermissionAction]:
    """责任等级 → 动作集。resp 为 None（该阶段无责任）时返回空集。"""
    if resp is None:
        return set()
    return set(RESPONSIBILITY_ACTIONS.get(resp, set()))


@dataclass
class Membership:
    """某人在某个项目上、以某个单位身份参与的关系。"""

    project_id: str
    unit_code: str
    org_id: str | None = None
    data_scope: str = DataScope.PROJECT.value
    #: 项目级阶段覆盖。为空 → 用《管理流程》矩阵推出来的阶段（默认、推荐）。
    #: 非空 → 用项目自己的配置（个别项目责任划分与标准矩阵不同时才用）。
    stage_scope_override: set[str] | None = None
    valid_from: date | None = None
    valid_to: date | None = None

    @property
    def stages(self) -> set[str]:
        """该单位有责任的阶段。

        **默认从矩阵推导，不存库** —— 这是新模型最省事的地方：
        矩阵里写了哪些阶段，就自动有哪些阶段的权限，不用另配。
        个别项目需要偏离标准矩阵时，用 stage_scope 字段覆盖。
        """
        if self.stage_scope_override:
            return set(self.stage_scope_override)
        return set(stages_of_unit(self.unit_code).keys())

    def responsibility_in(self, stage_code: str | None) -> Responsibility | None:
        return responsibility_of(stage_code, self.unit_code)

    def covers_stage(self, stage_code: str | None) -> bool:
        if stage_code is None:
            return True
        return stage_code in self.stages

    def actions_in(self, stage_code: str | None) -> set[PermissionAction]:
        """本项目、本阶段下我拥有的动作。

        阶段为 None 表示"项目级动作"（如生成项目概况），
        取该单位在**任一**阶段的最大动作集，避免项目级操作被阶段卡住。
        """
        if stage_code is None:
            merged: set[PermissionAction] = set()
            for st in self.stages:
                merged |= actions_of(self.responsibility_in(st))
            return merged
        return actions_of(self.responsibility_in(stage_code))

    def allows(self, action: PermissionAction, stage_code: str | None = None) -> bool:
        return action in self.actions_in(stage_code)

    def is_primary(self, stage_code: str | None) -> bool:
        return self.responsibility_in(stage_code) is Responsibility.PRIMARY

    def responsibility_for_display(self) -> Responsibility | None:
        """展示用的责任等级 —— 取本人在所有参与阶段里最重的那一级。"""
        best: Responsibility | None = None
        for st in self.stages:
            r = self.responsibility_in(st)
            if r is None:
                continue
            if best is None or RESPONSIBILITY_ORDER[r] > RESPONSIBILITY_ORDER[best]:
                best = r
        return best


@dataclass
class Principal:
    """当前请求主体。"""

    user: AppUser
    memberships: list[Membership] = field(default_factory=list)
    is_superuser: bool = False

    # ---------- 身份 ----------

    @property
    def user_id(self) -> str:
        return self.user.id

    @property
    def display(self) -> str:
        """审计留痕用的"操作人"显示串 —— 姓名 + 工号。

        用户明确要求：所有操作都要能看出是谁做的，
        所以审计里存这个，而不是只存一个 uuid。
        """
        no = getattr(self.user, "employee_no", None)
        name = getattr(self.user, "name", None) or self.user.username
        return f"{name}（{no}）" if no else name

    @property
    def project_ids(self) -> set[str]:
        return {m.project_id for m in self.memberships}

    # ---------- 成员关系 ----------

    def memberships_in(self, project_id: str) -> list[Membership]:
        return [m for m in self.memberships if m.project_id == project_id]

    def units_in(self, project_id: str) -> set[str]:
        return {m.unit_code for m in self.memberships_in(project_id)}

    def membership(self, project_id: str) -> Membership | None:
        """取第一条 —— **仅供展示"主要身份"，不要用它做权限判断**。

        一个人同项目下可能有多个身份（例如施工单位同时兼监理），
        权限判断必须遍历全部成员关系取并集，用 can()。
        """
        ms = self.memberships_in(project_id)
        return ms[0] if ms else None

    def highest_responsibility(self, project_id: str) -> Responsibility | None:
        """我在本项目承担的最重责任 —— 界面显示"我的身份"用。"""
        best: Responsibility | None = None
        for m in self.memberships_in(project_id):
            r = m.responsibility_for_display()
            if r is None:
                continue
            if best is None or RESPONSIBILITY_ORDER[r] > RESPONSIBILITY_ORDER[best]:
                best = r
        return best

    # ---------- 三层校验总入口 ----------

    def can_access_project(self, project_id: str) -> bool:
        return self.is_superuser or project_id in self.project_ids

    def can(
        self, action: PermissionAction, project_id: str, stage_code: str | None = None
    ) -> bool:
        """三层校验。

        **遍历全部成员关系取并集**（任一满足即通过）。
        用户在项目 A 是设计单位、项目 B 是监理单位时，
        进 A 就只有设计单位的权限，不会被 B 放大。
        """
        if self.is_superuser:
            return True
        return any(m.allows(action, stage_code) for m in self.memberships_in(project_id))

    def visible_stages(self, project_id: str) -> set[StageCode]:
        """我在本项目能看到哪些阶段 —— 全部成员关系的并集。"""
        if self.is_superuser:
            return set(StageCode)
        out: set[StageCode] = set()
        for m in self.memberships_in(project_id):
            for st in m.stages:
                try:
                    out.add(StageCode(st))
                except ValueError:
                    continue
        return out

    def is_primary_of(self, project_id: str, stage_code: str) -> bool:
        """我是不是这个阶段的主办单位 —— 界面据此决定是否显示「上传/发布」。"""
        if self.is_superuser:
            return True
        return any(m.is_primary(stage_code) for m in self.memberships_in(project_id))

    def can_view_stage(self, project_id: str, stage_code: str) -> bool:
        """我能不能看到某阶段的内容 —— 阶段过滤的统一入口。

        与 can(VIEW, ...) 的区别：这里只判"阶段有没有责任"，
        不要求具体动作权限。用于列表类接口的阶段过滤。
        """
        if self.is_superuser:
            return True
        return stage_code in {s.value for s in self.visible_stages(project_id)}

    def responsibility_in_stage(
        self, project_id: str, stage_code: str | None
    ) -> Responsibility | None:
        """我在本项目某阶段的责任等级 —— 取全部身份里最重的那一级。

        用于给用户一句人话解释"你为什么不能做这个操作"。
        """
        if self.is_superuser:
            return Responsibility.PRIMARY
        best: Responsibility | None = None
        for m in self.memberships_in(project_id):
            r = m.responsibility_in(stage_code)
            if r is None:
                continue
            if best is None or RESPONSIBILITY_ORDER[r] > RESPONSIBILITY_ORDER[best]:
                best = r
        return best

    def max_secret_level(self, project_id: str) -> int:
        """可查看的最高敏感等级。

        规则：在本项目**任一阶段**有编辑权（即主办）即可看「受限」。
        """
        if self.is_superuser:
            return SECRET_ORDER[SecretLevel.SECRET]
        ms = self.memberships_in(project_id)
        if not ms:
            return -1
        if any(PermissionAction.EDIT in m.actions_in(None) for m in ms):
            return SECRET_ORDER[SecretLevel.RESTRICTED]
        return SECRET_ORDER[SecretLevel.INTERNAL]

    def can_view_secret(self, project_id: str, secret_level: str) -> bool:
        try:
            need = SECRET_ORDER[SecretLevel(secret_level)]
        except ValueError:
            need = SECRET_ORDER[SecretLevel.INTERNAL]
        return self.max_secret_level(project_id) >= need


# ============================================================
# 主体构建
# ============================================================


def build_principal(db: Session, user: AppUser) -> Principal:
    """加载用户全部有效成员关系，构建 Principal。

    有效期过滤在这里做：人员借调、临时参与靠 valid_from / valid_to 控制。
    """
    today = date.today()
    rows = db.execute(
        select(ProjectMember).where(
            ProjectMember.user_id == user.id,
            ProjectMember.revoked_at.is_(None),
            or_(ProjectMember.valid_from.is_(None), ProjectMember.valid_from <= today),
            or_(ProjectMember.valid_to.is_(None), ProjectMember.valid_to >= today),
        )
    ).scalars().all()

    memberships = [
        Membership(
            project_id=r.project_id,
            unit_code=r.role_code,          # 列名沿用 role_code，语义已是"参与单位"
            org_id=r.org_id,
            data_scope=r.data_scope or DataScope.PROJECT.value,
            stage_scope_override=_parse_stage_override(r.stage_scope),
            valid_from=r.valid_from,
            valid_to=r.valid_to,
        )
        for r in rows
    ]
    return Principal(user=user, memberships=memberships, is_superuser=user.is_superuser)


def _parse_stage_override(raw: str | None) -> set[str] | None:
    """解析项目级的阶段覆盖配置。

    "ALL"、空、或与矩阵一致时返回 None（表示"按矩阵来"）。
    这样默认行为永远是标准矩阵，不会被历史数据搞乱。
    """
    if not raw or not raw.strip():
        return None
    val = raw.strip().upper()
    if val == "ALL":
        return None
    out: set[str] = set()
    for part in raw.split(","):
        p = part.strip()
        if p:
            out.add(p)
    return out or None


# ============================================================
# 查询层过滤（过滤发生在 SQL，不是拿到数据之后）
# ============================================================


def scoped_project_query(principal: Principal):
    """当前用户可见项目的查询。

    **过滤在 SQL 层完成** —— 这是"AI 检索先过权限过滤再检索"的前提。
    """
    stmt = select(Project)
    if principal.is_superuser:
        return stmt.order_by(Project.created_at.desc())

    if not principal.project_ids:
        return stmt.where(Project.id.is_(None))   # 无成员关系 → 空集（而非全部）

    conditions = []
    for m in principal.memberships:
        cond = [Project.id == m.project_id]
        if m.data_scope == DataScope.ORG_ONLY and m.org_id:
            cond.append(Project.owner_org_id == m.org_id)
        conditions.append(and_(*cond))

    return stmt.where(or_(*conditions)).order_by(Project.created_at.desc())


def ensure_project_access(principal: Principal, project_id: str) -> None:
    if not principal.can_access_project(project_id):
        raise PermissionError(f"无权访问项目 {project_id}")


def ensure_action(
    principal: Principal, action: PermissionAction, project_id: str, stage_code: str | None = None
) -> None:
    if not principal.can(action, project_id, stage_code):
        units = "、".join(sorted(principal.units_in(project_id))) or "无参与身份"
        raise PermissionError(
            f"你在本项目以「{units}」参与，"
            f"在阶段 {stage_code or '全部'} 无权执行 {action}"
        )


def resolve_org_ids(db: Session, user_id: str) -> list[str]:
    return list(
        db.execute(select(UserOrg.org_id).where(UserOrg.user_id == user_id)).scalars().all()
    )


# ============================================================
# 阶段责任概览（界面"这个阶段谁负责"用）
# ============================================================


def stage_responsibility_board() -> list[dict]:
    """七阶段的负责情况总览。

    回答核心问题：**这个阶段谁负责。**
    """
    board: list[dict] = []
    for st in STAGE_ORDER:
        units = RESPONSIBILITY_MATRIX.get(st.value, {})
        board.append(
            {
                "stage_code": st.value,
                "primary_unit": primary_unit_of_stage(st.value),
                "units": [
                    {"unit_code": u, "responsibility": r.value}
                    for u, r in sorted(
                        units.items(), key=lambda kv: -RESPONSIBILITY_ORDER[kv[1]]
                    )
                ],
            }
        )
    return board
