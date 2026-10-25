"""问题管理与闭环。

对应设计 PPT 第 8 页那条链路：
  问题描述 → 查询 → 分析识别 → 建议 → 执行 → 验证 → 闭环 → 知识沉淀

**这条链要有表承载，不能只做在聊天窗口里。**
"知识沉淀"是产品越用越有价值的关键：已闭环问题自动入库，可被 AI 检索引用。
"""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, IdMixin, TimestampMixin


class Issue(Base, IdMixin, TimestampMixin):
    """问题。来源可以是校审、现场、检测、自检。"""

    __tablename__ = "issue"

    project_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("project.id", ondelete="CASCADE"), nullable=False, index=True
    )
    stage_code: Mapped[str] = mapped_column(String(32), nullable=False, index=True)

    issue_no: Mapped[str | None] = mapped_column(String(64), index=True)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)

    # 来源：REVIEW 校审 / SITE 现场 / INSPECTION 检测 / SELF 自检 / MONITOR 监测 / AI AI提示
    source: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    # 引用 dict_item(ISSUE_TYPE)
    issue_type_id: Mapped[str | None] = mapped_column(String(32), ForeignKey("dict_item.id"), index=True)
    issue_type_name: Mapped[str | None] = mapped_column(String(100))

    severity: Mapped[str] = mapped_column(
        String(16), default="NORMAL", nullable=False, index=True, comment="HIGH / NORMAL / LOW"
    )
    # IssueStatus
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)

    # 关联对象（哪根桩 / 哪份文件 / 哪个变更）
    related_pile_id: Mapped[str | None] = mapped_column(String(32), index=True)
    related_version_id: Mapped[str | None] = mapped_column(String(32), index=True)
    related_change_id: Mapped[str | None] = mapped_column(String(32), index=True)

    raise_by: Mapped[str | None] = mapped_column(String(32), ForeignKey("app_user.id"), index=True)
    raise_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    assignee: Mapped[str | None] = mapped_column(String(32), ForeignKey("app_user.id"), index=True)
    due_date: Mapped[date | None] = mapped_column(Date, index=True)

    # 验证（闭环判定）
    verified_by: Mapped[str | None] = mapped_column(String(32), ForeignKey("app_user.id"))
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    verify_conclusion: Mapped[str | None] = mapped_column(Text, comment="验证依据与结论")

    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    closed_by: Mapped[str | None] = mapped_column(String(32), ForeignKey("app_user.id"))

    # 知识沉淀：闭环后转为知识库条目，供后续项目与 AI 检索
    is_knowledge: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    knowledge_summary: Mapped[str | None] = mapped_column(Text)

    actions: Mapped[list["IssueAction"]] = relationship(
        back_populates="issue", cascade="all, delete-orphan", order_by="IssueAction.created_at"
    )


class IssueAction(Base, IdMixin, TimestampMixin):
    """问题处理记录。IssueActionType 直接对应 PPT 第 8 页的链路各环节。"""

    __tablename__ = "issue_action"

    issue_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("issue.id", ondelete="CASCADE"), nullable=False, index=True
    )
    project_id: Mapped[str] = mapped_column(String(32), nullable=False, index=True)

    # IssueActionType：DESCRIBE/QUERY/ANALYZE/SUGGEST/EXECUTE/VERIFY/CLOSE/KNOWLEDGE
    action_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)

    # AI 生成的建议必须带依据引用
    is_ai_generated: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    ai_citation: Mapped[str | None] = mapped_column(Text, comment="AI 建议的引用来源")

    actor: Mapped[str | None] = mapped_column(String(32), ForeignKey("app_user.id"), index=True)
    acted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    attachment_version_id: Mapped[str | None] = mapped_column(String(32))
    sort: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    issue: Mapped[Issue] = relationship(back_populates="actions")
