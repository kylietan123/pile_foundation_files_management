"""AI 知识与对话，以及审计日志。

=== AI 治理规则（与《公共层契约》§4 一致，代码必须落实）===

1. 切片按**工程语义结构**（土层、桩型、荷载、检测项、章节条号），不是固定字数切。
   每个 knowledge_chunk 必须挂 project_id / stage_code / discipline / doc_type /
   source_version_id / section_path。
2. **只把 PUBLISHED 版本入知识库。** 草稿和审批中的文件不进。
3. **AI 检索必须先过权限过滤，再检索。**
   严禁"先检索全库再过滤结果"——那样模型已经看到内容了。
4. **会话上下文严格限定在当前项目**，内部试用期不允许跨项目检索。
5. 每次回答必须带 ai_citation，**没有引用的 AI 回答不允许展示给用户**。
6. 所有 prompt / 回答 / 引用 / 用户反馈入库保留 ≥ 90 天。

=== 回答格式（强制，缺一即视为无效回答）===
  【结论】  直接回答
  【依据】  引用的文件版本 + 页码/条号（可点击跳转到原文）
  【不确定性】 信息不足、规范未覆盖、需人工判断的地方
  【责任声明】 本回答由 AI 辅助生成，仅供设计参考，须由注册工程师复核确认
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.types import json_obj
from app.models.base import Base, IdMixin, TimestampMixin


# ============================================================
# AI 知识库
# ============================================================


class KnowledgeChunk(Base, IdMixin, TimestampMixin):
    """知识块。

    project_id 为空表示全局规范库（全员可见）。
    embedding 在开发期用 SQLite 时不存（或存 JSON），
    切换到 PostgreSQL + pgvector 后改为 Vector(1024)。
    """

    __tablename__ = "knowledge_chunk"

    project_id: Mapped[str | None] = mapped_column(
        String(32), ForeignKey("project.id", ondelete="CASCADE"), index=True,
        comment="空 = 全局规范库"
    )
    source_version_id: Mapped[str | None] = mapped_column(
        String(32), ForeignKey("document_version.id", ondelete="CASCADE"), index=True
    )

    stage_code: Mapped[str | None] = mapped_column(String(32), index=True)
    discipline: Mapped[str | None] = mapped_column(String(32), index=True)
    doc_type: Mapped[str | None] = mapped_column(String(64), index=True)
    # 章节路径，如 "第4章/4.3.2"，用于精确引用
    section_path: Mapped[str | None] = mapped_column(String(300), index=True)
    page_no: Mapped[int | None] = mapped_column(Integer)

    text: Mapped[str] = mapped_column(Text, nullable=False)
    token_count: Mapped[int | None] = mapped_column(Integer)
    chunk_index: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # 敏感等级继承自源文件，检索前用于权限过滤
    secret_level: Mapped[str] = mapped_column(String(32), default="INTERNAL", nullable=False, index=True)

    # 向量：开发期存 JSON，生产切 pgvector
    embedding_json: Mapped[dict | None] = mapped_column(json_obj())
    embedding_model: Mapped[str | None] = mapped_column(String(64))
    indexed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


# ============================================================
# AI 对话
# ============================================================


class AIConversation(Base, IdMixin, TimestampMixin):
    """会话。**必须绑定 project_id，内部试用期禁止跨项目。**"""

    __tablename__ = "ai_conversation"

    project_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("project.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("app_user.id", ondelete="CASCADE"), nullable=False, index=True
    )
    stage_code: Mapped[str | None] = mapped_column(String(32), index=True)

    title: Mapped[str | None] = mapped_column(String(200))
    # 本次会话允许检索的范围快照（权限过滤依据，避免权限变更后越权）
    scope_snapshot: Mapped[dict | None] = mapped_column(json_obj())

    message_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    archived: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    messages: Mapped[list["AIMessage"]] = relationship(
        back_populates="conversation", cascade="all, delete-orphan", order_by="AIMessage.created_at"
    )


class AIMessage(Base, IdMixin, TimestampMixin):
    """消息。"""

    __tablename__ = "ai_message"

    conversation_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("ai_conversation.id", ondelete="CASCADE"), nullable=False, index=True
    )
    project_id: Mapped[str] = mapped_column(String(32), nullable=False, index=True)

    # user / assistant / system
    role: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)

    # 四段式回答的拆分字段（便于前端结构化展示）
    conclusion: Mapped[str | None] = mapped_column(Text)
    uncertainty: Mapped[str | None] = mapped_column(Text, comment="不确定性说明")
    disclaimer: Mapped[str | None] = mapped_column(
        Text, default="本回答由 AI 辅助生成，仅供设计参考，须由注册工程师复核确认"
    )
    has_citation: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False, index=True,
        comment="无引用的回答不允许展示给用户 —— 前端据此拦截"
    )

    model: Mapped[str | None] = mapped_column(String(64))
    provider: Mapped[str | None] = mapped_column(String(32))
    prompt_tokens: Mapped[int | None] = mapped_column(Integer)
    completion_tokens: Mapped[int | None] = mapped_column(Integer)
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    error: Mapped[str | None] = mapped_column(Text)

    # 用户反馈
    feedback: Mapped[str | None] = mapped_column(String(16), comment="USEFUL / USELESS")
    feedback_note: Mapped[str | None] = mapped_column(Text)

    conversation: Mapped[AIConversation] = relationship(back_populates="messages")
    citations: Mapped[list["AICitation"]] = relationship(
        back_populates="message", cascade="all, delete-orphan"
    )


class AICitation(Base, IdMixin, TimestampMixin):
    """引用。**AI 可信度的全部来源。**"""

    __tablename__ = "ai_citation"

    message_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("ai_message.id", ondelete="CASCADE"), nullable=False, index=True
    )
    chunk_id: Mapped[str | None] = mapped_column(
        String(32), ForeignKey("knowledge_chunk.id", ondelete="SET NULL"), index=True
    )
    source_version_id: Mapped[str | None] = mapped_column(String(32), index=True)

    # 引用定位：页码 / 条号 / 表号，前端据此跳转原文
    locator: Mapped[str | None] = mapped_column(String(200))
    quoted_text: Mapped[str | None] = mapped_column(Text)
    score: Mapped[float | None] = mapped_column(Float, comment="相关性得分")
    sort: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    message: Mapped[AIMessage] = relationship(back_populates="citations")


# ============================================================
# 审计
# ============================================================


class AuditLog(Base, IdMixin, TimestampMixin):
    """审计日志。

    **内部试用的硬要求**：谁在什么时候改了什么、下载了什么，可查、可导出审计报表。
    任何写操作都必须留痕。禁止物理删除本表记录。
    """

    __tablename__ = "audit_log"

    project_id: Mapped[str | None] = mapped_column(String(32), index=True)
    stage_code: Mapped[str | None] = mapped_column(String(32), index=True)

    actor: Mapped[str | None] = mapped_column(String(32), ForeignKey("app_user.id"), index=True)
    actor_name: Mapped[str | None] = mapped_column(String(64), comment="冗余，便于审计报表展示")
    actor_org_id: Mapped[str | None] = mapped_column(String(32))

    action: Mapped[str] = mapped_column(
        String(64), nullable=False, index=True,
        comment="LOGIN/CREATE/UPDATE/DELETE/SUBMIT/APPROVE/RETURN/PUBLISH/VOID/DOWNLOAD/EXPORT/GRANT/VIEW_SECRET"
    )
    target_type: Mapped[str | None] = mapped_column(String(64), index=True)
    target_id: Mapped[str | None] = mapped_column(String(32), index=True)
    target_name: Mapped[str | None] = mapped_column(String(300))

    before: Mapped[dict | None] = mapped_column(json_obj())
    after: Mapped[dict | None] = mapped_column(json_obj())

    detail: Mapped[str | None] = mapped_column(Text)
    ip: Mapped[str | None] = mapped_column(String(64))
    user_agent: Mapped[str | None] = mapped_column(String(300))
    success: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
