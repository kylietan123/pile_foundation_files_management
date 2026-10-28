"""文件、版本、授权 —— 全平台唯一的文件与版本引擎。

**铁律：document_version 一旦进入 PUBLISHED，记录不可修改、文件字节不可覆盖。
修改 = 新建版本。**

内容寻址去重：file_id = sha256(content)，相同文件只存一份。

状态机：
  草稿 → 校核中 → 审核中 → 已批准 → 已发布 → 已作废
  修订循环：已发布 --发起修订--> 修订中 --> 校核中 …

四条强制校验（后端拦截，不依赖前端）：
  1. DRAFT/CHECKING/REVIEWING 等未发布版本不可被下游引用
  2. 同一 document 不允许同时存在两个处于审批中的版本（防版本分叉）
  3. PUBLISHED 不可回退，要改就发新版本
  4. 同一 document 同一时刻最多一个 PUBLISHED 版本
  另外：作废必须填原因，且不允许物理删除。
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, IdMixin, TimestampMixin


class FileObject(Base, TimestampMixin):
    """物理文件（内容寻址去重）。

    主键就是 sha256，相同内容的文件全平台只存一份。
    原始上传文件不可变；所有"编辑"都是新版本、新文件。
    """

    __tablename__ = "file_object"

    file_id: Mapped[str] = mapped_column(
        String(64), primary_key=True, comment="sha256(content)，内容寻址"
    )
    size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    mime: Mapped[str | None] = mapped_column(String(128))
    ext: Mapped[str | None] = mapped_column(String(16))
    original_name: Mapped[str | None] = mapped_column(String(300), comment="首次上传时的文件名")
    # 相对 STORAGE_ROOT 的路径，禁止对外暴露
    storage_key: Mapped[str] = mapped_column(String(300), nullable=False)
    ref_count: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    created_by: Mapped[str | None] = mapped_column(String(32), ForeignKey("app_user.id"))


class Document(Base, IdMixin, TimestampMixin):
    """逻辑文档。一个 document 下可以有多个 version。

    例：document = "桩基平面布置图"，其 versions = V1.0 / V1.1 / V2.0。
    """

    __tablename__ = "document"
    __table_args__ = (
        UniqueConstraint("project_id", "doc_no", "discipline", name="uq_document_no"),
    )

    project_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("project.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # StageCode：本文件属于哪个阶段
    stage_code: Mapped[str] = mapped_column(String(32), nullable=False, index=True)

    # 引用 dict_item(DOC_TYPE)，如 设计说明/计算书/布置图/配筋图/施工图
    category_id: Mapped[str | None] = mapped_column(String(32), ForeignKey("dict_item.id"), index=True)
    category_name: Mapped[str | None] = mapped_column(String(100))

    title: Mapped[str] = mapped_column(String(300), nullable=False, index=True)
    doc_no: Mapped[str | None] = mapped_column(String(100), index=True, comment="图号/文件编号")
    # 标准清单条目码（document_catalog.json 的 doc_code，如 "1.1.1"）。关联"待上传清单"。
    doc_code: Mapped[str | None] = mapped_column(String(32), index=True)
    discipline: Mapped[str] = mapped_column(
        String(32), default="GENERAL", nullable=False, comment="专业：结构/岩土/建筑…"
    )
    # SecretLevel
    secret_level: Mapped[str] = mapped_column(String(32), default="INTERNAL", nullable=False, index=True)

    # 当前有效版本（冗余，便于列表页展示；以 version 表为准）
    current_version_id: Mapped[str | None] = mapped_column(String(32))
    published_version_no: Mapped[str | None] = mapped_column(String(32))

    created_by: Mapped[str | None] = mapped_column(String(32), ForeignKey("app_user.id"))
    remark: Mapped[str | None] = mapped_column(Text)

    versions: Mapped[list["DocumentVersion"]] = relationship(
        back_populates="document", cascade="all, delete-orphan", order_by="DocumentVersion.created_at"
    )


class DocumentChecklist(Base, IdMixin, TimestampMixin):
    """项目 × 标准清单条目 的落地状态。

    每个项目对清单里的每一类文档，都有三种状态之一：
      PENDING       —— 尚未上传（可带原因）
      UPLOADED      —— 已上传（上传时自动置此状态）
      NOT_REQUIRED  —— 本项目不需要（带原因）
    """

    __tablename__ = "document_checklist"
    __table_args__ = (
        UniqueConstraint("project_id", "doc_code", name="uq_checklist_doc"),
    )

    project_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("project.id", ondelete="CASCADE"), nullable=False, index=True
    )
    stage_code: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    doc_code: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="PENDING", nullable=False, index=True)
    reason: Mapped[str | None] = mapped_column(Text)
    updated_by: Mapped[str | None] = mapped_column(String(32), ForeignKey("app_user.id"))


class DocumentVersion(Base, IdMixin, TimestampMixin):
    """文件版本。状态机的载体。"""

    __tablename__ = "document_version"
    __table_args__ = (
        UniqueConstraint("document_id", "version_no", "revision", name="uq_document_version"),
    )

    document_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("document.id", ondelete="CASCADE"), nullable=False, index=True
    )
    project_id: Mapped[str] = mapped_column(String(32), nullable=False, index=True)

    version_no: Mapped[str] = mapped_column(String(32), nullable=False, comment="A/B/C 或 V1.0/V1.1")
    revision: Mapped[int] = mapped_column(Integer, default=0, nullable=False, comment="修订次")

    file_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("file_object.file_id"), nullable=False
    )

    # DocumentState
    state: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    change_summary: Mapped[str | None] = mapped_column(Text, comment="本版相对上版改了什么")
    remark: Mapped[str | None] = mapped_column(Text)

    created_by: Mapped[str | None] = mapped_column(String(32), ForeignKey("app_user.id"))
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    published_by: Mapped[str | None] = mapped_column(String(32), ForeignKey("app_user.id"))

    # 作废
    voided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    voided_by: Mapped[str | None] = mapped_column(String(32), ForeignKey("app_user.id"))
    void_reason: Mapped[str | None] = mapped_column(Text)

    # 修订来源：本版是为哪个变更/哪个旧版服务
    from_change_id: Mapped[str | None] = mapped_column(String(32), index=True)
    supersedes_version_id: Mapped[str | None] = mapped_column(String(32), index=True)

    # 自校标记：人员不足时的例外，必须显著标注并留痕
    is_self_checked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    self_check_reason: Mapped[str | None] = mapped_column(Text)

    document: Mapped[Document] = relationship(back_populates="versions")


class DocumentRelation(Base, IdMixin, TimestampMixin):
    """文件之间的引用关系。

    **变更影响分析的依据**：某个参数变了，通过这张表找出哪些图纸引用了旧版本。
    """

    __tablename__ = "document_relation"

    project_id: Mapped[str] = mapped_column(String(32), nullable=False, index=True)

    src_version_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("document_version.id", ondelete="CASCADE"), nullable=False, index=True
    )
    dst_version_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("document_version.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # REFERENCE 引用 / SUPERSEDE 替代 / RELATED 关联
    rel_type: Mapped[str] = mapped_column(String(32), nullable=False, default="REFERENCE")
    note: Mapped[str | None] = mapped_column(Text)


class DocumentAccess(Base, IdMixin, TimestampMixin):
    """特殊授权（跨单位可见性）。

    默认：参与单位只能看本项目、本阶段的文件。
    跨单位要看（如监理看检测数据），必须通过本表显式授权并记录 reason。
    """

    __tablename__ = "document_access"

    project_id: Mapped[str] = mapped_column(String(32), nullable=False, index=True)

    # 可以授权到 document 级别或 version 级别
    document_id: Mapped[str | None] = mapped_column(
        String(32), ForeignKey("document.id", ondelete="CASCADE"), index=True
    )
    version_id: Mapped[str | None] = mapped_column(
        String(32), ForeignKey("document_version.id", ondelete="CASCADE"), index=True
    )

    target_org_id: Mapped[str | None] = mapped_column(
        String(32), ForeignKey("organization.id", ondelete="CASCADE"), index=True
    )
    target_user_id: Mapped[str | None] = mapped_column(
        String(32), ForeignKey("app_user.id", ondelete="CASCADE"), index=True
    )

    # 逗号分隔的 PermissionAction：VIEW,DOWNLOAD,EDIT,EXPORT
    actions: Mapped[str] = mapped_column(String(100), nullable=False, default="VIEW")
    reason: Mapped[str] = mapped_column(Text, nullable=False, comment="必须填写授权原因")

    granted_by: Mapped[str | None] = mapped_column(String(32), ForeignKey("app_user.id"))
    valid_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
