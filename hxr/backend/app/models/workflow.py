"""工作流：模板、实例、任务。

统一承载三类审批业务：REVIEW 校审 / CHANGE 变更 / PUBLISH 发布。

三级校审（设计院制度）：
  CHECK 校核人 → REVIEW 审核人 → APPROVE 审定/批准人 → PUBLISH 发布
三者必须分离。人员不足需自校时走 SELF_CHECK 节点，
并把 DocumentVersion.is_self_checked 置为 True，前台显著标注、审计留痕。
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.types import json_arr
from app.models.base import Base, IdMixin, TimestampMixin


class WorkflowTemplate(Base, IdMixin, TimestampMixin):
    """流程模板。nodes 是节点定义数组。

    nodes 示例：
    [
      {"code":"CHECK",   "name":"校核", "role":"DESIGN_CHECKER",  "sort":1, "required":true},
      {"code":"REVIEW",  "name":"审核", "role":"DESIGN_REVIEWER", "sort":2, "required":true},
      {"code":"APPROVE", "name":"批准", "role":"DESIGN_APPROVER", "sort":3, "required":true},
      {"code":"PUBLISH", "name":"发布", "role":"DESIGN_APPROVER", "sort":4, "required":true}
    ]
    """

    __tablename__ = "workflow_template"

    code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    # WorkflowBizType
    biz_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    stage_code: Mapped[str | None] = mapped_column(String(32), index=True, comment="空=适用全部阶段")

    nodes: Mapped[list] = mapped_column(json_arr(), nullable=False, default=list)
    # 允许自校（人员不足的例外），默认关闭，开启后必须留痕
    allow_self_check: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_system: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)

    instances: Mapped[list["WorkflowInstance"]] = relationship(back_populates="template")


class WorkflowInstance(Base, IdMixin, TimestampMixin):
    """流程实例。biz_id 指向具体业务对象（版本 id / 变更 id）。"""

    __tablename__ = "workflow_instance"

    template_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("workflow_template.id"), nullable=False, index=True
    )
    project_id: Mapped[str] = mapped_column(String(32), nullable=False, index=True)

    # WorkflowBizType
    biz_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    biz_id: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    stage_code: Mapped[str | None] = mapped_column(String(32), index=True)

    # WorkflowStatus
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="RUNNING", index=True)
    current_node: Mapped[str | None] = mapped_column(String(32))
    round: Mapped[int] = mapped_column(Integer, default=1, nullable=False, comment="第几轮（退回后 +1）")

    initiator: Mapped[str] = mapped_column(String(32), ForeignKey("app_user.id"), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    template: Mapped[WorkflowTemplate] = relationship(back_populates="instances")
    tasks: Mapped[list["WorkflowTask"]] = relationship(
        back_populates="instance", cascade="all, delete-orphan", order_by="WorkflowTask.created_at"
    )


class WorkflowTask(Base, IdMixin, TimestampMixin):
    """审批任务。退回时**不覆盖历史意见**，而是新增一条任务记录。"""

    __tablename__ = "workflow_task"

    instance_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("workflow_instance.id", ondelete="CASCADE"), nullable=False, index=True
    )
    project_id: Mapped[str] = mapped_column(String(32), nullable=False, index=True)

    # WorkflowNodeCode
    node_code: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    node_name: Mapped[str | None] = mapped_column(String(64))
    round: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    assignee: Mapped[str | None] = mapped_column(String(32), ForeignKey("app_user.id"), index=True)
    assignee_role: Mapped[str | None] = mapped_column(String(32))

    # TaskAction：APPROVE / RETURN / REJECT，未处理时为 NULL
    action: Mapped[str | None] = mapped_column(String(32), index=True)
    comment: Mapped[str | None] = mapped_column(Text, comment="审批意见")

    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    acted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # 实际操作人。与 assignee 区分开：可能出现代批、管理员处理等情况，
    # 也是"校核/审核/批准必须分离"这条规则的判定依据。
    acted_by: Mapped[str | None] = mapped_column(
        String(32), ForeignKey("app_user.id"), index=True
    )

    # 自校留痕
    is_self_check: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    instance: Mapped[WorkflowInstance] = relationship(back_populates="tasks")
