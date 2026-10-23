"""项目、阶段、项目成员，以及桩基专业技术对象。

**project_member 是权限的最小单元，也是最重要的一张表。**
用户与项目的关联只能通过它，任何业务查询都必须能据此过滤。

**参数溯源**：design_param.source_version_id + source_locator
是"设计里每个参数都能点开看到来自哪份勘察报告哪一页哪张表"的实现基础。
`source_version_id` 指向 document_version（在 document.py 中定义），
这里刻意不建 ORM relationship，避免模块循环依赖。
"""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, IdMixin, TimestampMixin


class Project(Base, IdMixin, TimestampMixin):
    """项目。全平台数据的根节点 —— 一切业务数据都必须挂在项目下。"""

    __tablename__ = "project"

    project_no: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    short_name: Mapped[str | None] = mapped_column(String(64))

    location: Mapped[str | None] = mapped_column(String(200))
    province: Mapped[str | None] = mapped_column(String(32))
    city: Mapped[str | None] = mapped_column(String(32))

    owner_org_id: Mapped[str | None] = mapped_column(String(32), ForeignKey("organization.id"))
    main_design_org_id: Mapped[str | None] = mapped_column(String(32), ForeignKey("organization.id"))

    project_type: Mapped[str | None] = mapped_column(String(64), comment="商业综合体/住宅/超高层/产业园…")
    scale_desc: Mapped[str | None] = mapped_column(String(200), comment="桩基规模描述，如 桩数 860 根")
    description: Mapped[str | None] = mapped_column(Text)

    # StageCode 当前阶段值（冗余字段，便于列表页直接显示；以 stage 表为准）
    current_stage_code: Mapped[str] = mapped_column(String(32), nullable=False, index=True)

    plan_start: Mapped[date | None] = mapped_column(Date)
    plan_end: Mapped[date | None] = mapped_column(Date)
    actual_start: Mapped[date | None] = mapped_column(Date)
    actual_end: Mapped[date | None] = mapped_column(Date)

    # ProjectStatus
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)

    created_by: Mapped[str | None] = mapped_column(String(32), ForeignKey("app_user.id"))

    stages: Mapped[list["ProjectStage"]] = relationship(
        back_populates="project", cascade="all, delete-orphan", order_by="ProjectStage.sort"
    )
    members: Mapped[list["ProjectMember"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )


class ProjectStage(Base, IdMixin, TimestampMixin):
    """项目下的阶段实例。7 个阶段是同一个项目的 7 个环节，不是 7 个独立系统。"""

    __tablename__ = "project_stage"
    __table_args__ = (
        UniqueConstraint("project_id", "stage_code", name="uq_project_stage"),
    )

    project_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("project.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # StageCode
    stage_code: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    # StageStatus
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="NOT_STARTED")
    progress: Mapped[int] = mapped_column(Integer, default=0, nullable=False, comment="0-100")

    sort: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    plan_start: Mapped[date | None] = mapped_column(Date)
    plan_end: Mapped[date | None] = mapped_column(Date)
    actual_start: Mapped[date | None] = mapped_column(Date)
    actual_end: Mapped[date | None] = mapped_column(Date)

    owner_user_id: Mapped[str | None] = mapped_column(
        String(32), ForeignKey("app_user.id"), comment="本阶段负责人（三方分工用）"
    )
    remark: Mapped[str | None] = mapped_column(Text)

    project: Mapped[Project] = relationship(back_populates="stages")


class ProjectMember(Base, IdMixin, TimestampMixin):
    """项目参与人 —— 权限的最小单元。

    权限模型三层同时校验：
      第 1 层 角色 role_code  → 能不能做这个动作
      第 2 层 数据范围 data_scope → 能不能看这个项目
      第 3 层 阶段范围 stage_scope → 能不能看这个阶段

    **一份配置，全局一致。** 不需要为 7 个阶段各配一遍权限。
    """

    __tablename__ = "project_member"
    __table_args__ = (
        UniqueConstraint("project_id", "user_id", "role_code", name="uq_project_member"),
    )

    project_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("project.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("app_user.id", ondelete="CASCADE"), nullable=False, index=True
    )
    org_id: Mapped[str | None] = mapped_column(
        String(32), ForeignKey("organization.id"), comment="以哪个单位的身份参与本项目"
    )

    # RoleCode
    role_code: Mapped[str] = mapped_column(String(32), nullable=False, index=True)

    # 阶段范围：逗号分隔的 StageCode，空字符串或 ALL 表示全部阶段
    stage_scope: Mapped[str] = mapped_column(
        String(200), default="ALL", nullable=False, comment="ALL 或逗号分隔的 StageCode"
    )
    # DataScope
    data_scope: Mapped[str] = mapped_column(String(32), default="PROJECT", nullable=False)

    # 项目级责任覆盖，格式如 "CONSTRUCTION=PRIMARY"，逗号分隔多个阶段。
    # 为空时完全按《管理流程》矩阵推导，不影响标准项目。
    responsibility_override: Mapped[str | None] = mapped_column(
        String(300), comment="阶段码=责任等级，逗号分隔；仅个别项目需要偏离矩阵时使用"
    )

    valid_from: Mapped[date | None] = mapped_column(Date)
    valid_to: Mapped[date | None] = mapped_column(Date)

    granted_by: Mapped[str | None] = mapped_column(String(32), ForeignKey("app_user.id"))
    granted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    remark: Mapped[str | None] = mapped_column(Text)

    project: Mapped[Project] = relationship(back_populates="members")


# ============================================================
# 桩基专业对象：跨越 勘察 → 设计 → 施工 → 验收
# 这些对象是"工程对象"，与"文件"是两类不同的东西。
# 通用文档系统管理文件；本平台管理工程对象及它们之间的引用关系。
# ============================================================


class SoilLayer(Base, IdMixin, TimestampMixin):
    """土层。来自勘察阶段，被设计阶段引用。"""

    __tablename__ = "soil_layer"
    __table_args__ = (
        UniqueConstraint("project_id", "layer_no", name="uq_soil_layer"),
    )

    project_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("project.id", ondelete="CASCADE"), nullable=False, index=True
    )
    layer_no: Mapped[str] = mapped_column(String(32), nullable=False, comment="层号，如 ① ② ③")
    name: Mapped[str] = mapped_column(String(100), nullable=False, comment="岩土名称")

    top_elev: Mapped[float | None] = mapped_column(Float, comment="层顶标高 (m)")
    bottom_elev: Mapped[float | None] = mapped_column(Float, comment="层底标高 (m)")
    thickness: Mapped[float | None] = mapped_column(Float, comment="层厚 (m)")

    # 溯源：本层数据来自哪份勘察报告的哪个版本
    source_version_id: Mapped[str | None] = mapped_column(String(32), index=True)
    source_locator: Mapped[str | None] = mapped_column(String(200), comment="如 P.15 表5-2")

    description: Mapped[str | None] = mapped_column(Text)


class SoilProperty(Base, IdMixin, TimestampMixin):
    """土层物理力学参数。每个参数独立成行，便于逐项溯源与核验。"""

    __tablename__ = "soil_property"
    __table_args__ = (
        UniqueConstraint("layer_id", "prop_code", "source_version_id", name="uq_soil_property"),
    )

    project_id: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    layer_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("soil_layer.id", ondelete="CASCADE"), nullable=False, index=True
    )

    prop_code: Mapped[str] = mapped_column(
        String(32), nullable=False, comment="gamma/c/phi/Es/fak/qsik/qpk…"
    )
    prop_name: Mapped[str | None] = mapped_column(String(64))
    value: Mapped[float] = mapped_column(Float, nullable=False)
    unit: Mapped[str | None] = mapped_column(String(16))

    source_version_id: Mapped[str | None] = mapped_column(String(32), index=True)
    source_locator: Mapped[str | None] = mapped_column(String(200))

    verified_by: Mapped[str | None] = mapped_column(String(32), ForeignKey("app_user.id"))
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class DesignParam(Base, IdMixin, TimestampMixin):
    """设计参数库 —— 参数溯源链的核心表。

    每个参数固定 5 个业务字段：参数名 / 数值 / 单位 / 来源文件与位置 / 核验状态。
    下游任何引用（计算、图纸、变更影响分析）都必须能回到这里。
    """

    __tablename__ = "design_param"
    __table_args__ = (
        UniqueConstraint("project_id", "param_code", name="uq_design_param"),
    )

    project_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("project.id", ondelete="CASCADE"), nullable=False, index=True
    )
    stage_code: Mapped[str | None] = mapped_column(String(32), index=True)

    param_code: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    param_name: Mapped[str] = mapped_column(String(128), nullable=False)
    param_group: Mapped[str | None] = mapped_column(
        String(64), comment="场地与地层 / 荷载与上部结构 / 边界与约束"
    )

    value_text: Mapped[str | None] = mapped_column(String(200))
    value_num: Mapped[float | None] = mapped_column(Float)
    unit: Mapped[str | None] = mapped_column(String(16))

    # ---- 溯源链 ----
    source_type: Mapped[str | None] = mapped_column(
        String(32), comment="DOCUMENT 文件 / MANUAL 人工录入 / CALC 计算得出"
    )
    source_version_id: Mapped[str | None] = mapped_column(String(32), index=True)
    source_locator: Mapped[str | None] = mapped_column(String(200), comment="页码/表号/条号")

    # ---- 核验状态 ----
    verify_status: Mapped[str] = mapped_column(
        String(32), default="PENDING", nullable=False, index=True,
        comment="PENDING 待核验 / VERIFIED 已核验 / MODIFIED 已修改 / DOUBTFUL 存疑 / STALE 来源已失效",
    )
    required: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    verified_by: Mapped[str | None] = mapped_column(String(32), ForeignKey("app_user.id"))
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    verify_note: Mapped[str | None] = mapped_column(Text)

    locked: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False,
        comment="设计输入锁定标记。锁定后如需修改必须走变更流程",
    )
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    locked_by: Mapped[str | None] = mapped_column(String(32), ForeignKey("app_user.id"))


class Pile(Base, IdMixin, TimestampMixin):
    """桩位。设计阶段确定，施工阶段回填实际值，验收与监测阶段引用。"""

    __tablename__ = "pile"
    __table_args__ = (
        UniqueConstraint("project_id", "pile_no", name="uq_pile"),
    )

    project_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("project.id", ondelete="CASCADE"), nullable=False, index=True
    )
    pile_no: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    # 统一 ID：直接引用 dict_item.id，各阶段共用同一桩型
    pile_type_id: Mapped[str | None] = mapped_column(
        String(32), ForeignKey("dict_item.id"), index=True,
        comment="统一 ID：引用 dict_item(PILE_TYPE)，各阶段共用"
    )
    pile_type_name: Mapped[str | None] = mapped_column(String(100), comment="冗余，便于列表展示")

    x: Mapped[float | None] = mapped_column(Float)
    y: Mapped[float | None] = mapped_column(Float)
    z: Mapped[float | None] = mapped_column(Float, comment="桩顶标高 (m)")

    design_length: Mapped[float | None] = mapped_column(Float, comment="设计桩长 (m)")
    actual_length: Mapped[float | None] = mapped_column(Float, comment="实际桩长 (m)，施工阶段回填")
    design_diameter: Mapped[float | None] = mapped_column(Float, comment="设计桩径 (mm)")

    design_capacity: Mapped[float | None] = mapped_column(Float, comment="设计单桩承载力特征值 (kN)")
    actual_capacity: Mapped[float | None] = mapped_column(Float, comment="实测承载力 (kN)")

    zone: Mapped[str | None] = mapped_column(String(64), comment="分区/楼栋，如 1#楼、A区")
    # 设计/施工/验收 状态流转
    status: Mapped[str] = mapped_column(
        String(32), default="DESIGNED", nullable=False, index=True,
        comment="DESIGNED 已设计 / CONSTRUCTING 施工中 / CONSTRUCTED 已施工 / ACCEPTED 已验收",
    )
    constructed_at: Mapped[date | None] = mapped_column(Date, comment="施工日期，变更影响分析要用")

    remark: Mapped[str | None] = mapped_column(Text)
