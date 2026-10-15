"""设计变更与影响分析。

**这是设计阶段最有价值的部分，也是安全价值的落点。**

变更批准后必须执行的动作（缺一不算完成）：
  1. 生成新版本文件（旧版本自动标为被替代）
  2. 更新 change_impact 中每条影响的处理状态
  3. 通知所有受影响单位（写入消息 + audit_log）

其中 impact_target_type = CONSTRUCTED_PART（已施工部位受影响）是最高风险项，
需要立即通知施工方与监理。
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.types import json_obj
from app.models.base import Base, IdMixin, TimestampMixin


class ChangeRequest(Base, IdMixin, TimestampMixin):
    """设计变更申请。"""

    __tablename__ = "change_request"
    __table_args__ = ()

    project_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("project.id", ondelete="CASCADE"), nullable=False, index=True
    )
    stage_code: Mapped[str] = mapped_column(String(32), nullable=False, index=True)

    change_no: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(300), nullable=False)

    # ChangeCategory 字典值：勘察资料/业主要求/规范更新/施工条件/设计优化
    category: Mapped[str | None] = mapped_column(String(32), index=True)
    reason: Mapped[str] = mapped_column(Text, nullable=False, comment="变更原因，必填")
    description: Mapped[str | None] = mapped_column(Text)

    # ChangeState —— 变更状态。刻意不叫 status：
    # 项目/阶段用 status，变更用 state，避免两个同义字段并存造成混乱。
    state: Mapped[str] = mapped_column(String(32), nullable=False, index=True)

    origin_version_id: Mapped[str | None] = mapped_column(
        String(32), index=True, comment="被变更的原设计版本"
    )
    new_version_id: Mapped[str | None] = mapped_column(
        String(32), index=True, comment="变更后生成的新版本"
    )

    # 影响统计（冗余，便于列表页展示与预警）
    impact_scope: Mapped[dict | None] = mapped_column(json_obj())
    impact_pile_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    impact_constructed_count: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False, comment="涉及已施工桩位数量，>0 需立即通知"
    )
    impact_cost_delta: Mapped[float | None] = mapped_column(Float, comment="预估成本变化 (元)")
    impact_schedule_days: Mapped[int | None] = mapped_column(Integer, comment="预估工期影响 (天)")

    initiator: Mapped[str | None] = mapped_column(String(32), ForeignKey("app_user.id"), index=True)
    approver: Mapped[str | None] = mapped_column(String(32), ForeignKey("app_user.id"))

    workflow_instance_id: Mapped[str | None] = mapped_column(String(32), index=True)

    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    due_date: Mapped[Date | None] = mapped_column(Date)

    impacts: Mapped[list["ChangeImpact"]] = relationship(
        back_populates="change", cascade="all, delete-orphan"
    )


class ChangeImpact(Base, IdMixin, TimestampMixin):
    """变更影响明细。**未全部闭环则变更不可关闭。**"""

    __tablename__ = "change_impact"

    change_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("change_request.id", ondelete="CASCADE"), nullable=False, index=True
    )
    project_id: Mapped[str] = mapped_column(String(32), nullable=False, index=True)

    # ImpactTargetType：PILE / CALCULATION / DRAWING / CONSTRUCTED_PART / COST / SCHEDULE
    target_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    target_id: Mapped[str | None] = mapped_column(String(32), index=True)
    target_name: Mapped[str | None] = mapped_column(String(300))

    impact_desc: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[str] = mapped_column(
        String(16), default="NORMAL", nullable=False, index=True, comment="HIGH / NORMAL / LOW"
    )
    # 已施工部位受影响 → 最高风险，需立即通知
    requires_immediate_notice: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    handled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    handled_by: Mapped[str | None] = mapped_column(String(32), ForeignKey("app_user.id"))
    handled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    handle_note: Mapped[str | None] = mapped_column(Text)

    change: Mapped[ChangeRequest] = relationship(back_populates="impacts")
