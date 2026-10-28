"""桩基选型方案（设计阶段的选型结论与留痕）。

一个项目一条记录：条件 + 建议 + 人工确认后的最终桩型与桩参数。
选型是设计阶段的**依据性文件**，所以要存库留痕（谁确认、什么时候确认），
而不是每次打开页面重新算一遍。

JSON 字段一律用 `json_obj()`（可原地修改且 SQLite / PostgreSQL 行为一致）。
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.types import json_obj
from app.models.base import Base, IdMixin, TimestampMixin


class PileSelection(Base, IdMixin, TimestampMixin):
    """项目桩基选型方案。

    状态：
      DRAFT      —— 已算出/已保存草稿，还在校对
      CONFIRMED  —— 设计人确认，作为设计输入的依据
    """

    __tablename__ = "pile_selection"

    project_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("project.id", ondelete="CASCADE"),
        nullable=False, unique=True, index=True,
    )
    stage_code: Mapped[str] = mapped_column(
        String(32), default="DESIGN", nullable=False, index=True
    )

    # ---- 输入 ----
    #: 项目条件：地铁保护区/内环/临近高架/密集建筑/工期/成本/地下层数/塔楼高度…
    conditions: Mapped[dict] = mapped_column(json_obj(), nullable=False)
    #: 勘察参数（可选）：承载力估算表行、地层、报告提取的桩参数
    geo: Mapped[dict | None] = mapped_column(json_obj())
    #: 建筑概况：容积率、用地/地上/地下/总面积、单体数、层数、覆土、折算厚度…
    overview: Mapped[dict | None] = mapped_column(json_obj())
    #: 非主楼数据（CAD 实测）：单/双层投影面积、塔楼投影、柱网、双层主楼建面
    calc_inputs: Mapped[dict | None] = mapped_column(json_obj())

    # ---- 结论 ----
    #: 主楼承压桩：{type_name, label, params}
    main: Mapped[dict] = mapped_column(json_obj(), nullable=False)
    #: 纯地下室桩：{type_name, label, params}
    base: Mapped[dict] = mapped_column(json_obj(), nullable=False)
    #: 引擎给出的完整建议快照（含各桩型评分与排除原因），便于事后解释"为什么这么选"
    snapshot: Mapped[dict | None] = mapped_column(json_obj())
    #: 选型理由（报告口径的一段话）
    reason: Mapped[str | None] = mapped_column(Text)

    # ---- 输出：桩基评估报告（纯规则拼接的 TXT 全文）----
    report_text: Mapped[str | None] = mapped_column(Text)
    report_generated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    #: 生成报告时用的元信息（日期/依据文件/标题），便于重出时保持一致
    report_meta: Mapped[dict | None] = mapped_column(json_obj())

    status: Mapped[str] = mapped_column(String(32), default="DRAFT", nullable=False, index=True)
    confirmed_by: Mapped[str | None] = mapped_column(String(32), ForeignKey("app_user.id"))
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    remark: Mapped[str | None] = mapped_column(Text)
