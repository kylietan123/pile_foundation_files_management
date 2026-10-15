"""模型包。

**新增模型必须在这里 import，否则 Alembic autogenerate 检测不到。**

──── 关于已移除的模型（2026-10 方向调整）────

原设计包含成本、进度、监测数据三组共 12 张表：

    cost_item / cost_actual / schedule_task / progress_report   （成本与进度）
    monitor_point / monitor_reading / monitor_threshold / monitor_alarm  （监测数据）

会上确定平台核心是**文档管理**（解决文件易丢、责任难追），
不做成本与进度管理；监测结果本身以**文件**形式归档，不需要结构化点位表。
这 12 张表当时均为 0 行、无任何业务代码引用，已连同模型一并移除。

**如需恢复**：迁移 `0002_drop_unused_business_tables` 的 downgrade 可重建表结构，
模型定义见 git 历史（commit c3cea6f 之前的 `models/cost.py` 与 `models/monitoring.py`）。
"""
from app.models.ai import (
    AICitation,
    AIConversation,
    AIMessage,
    AuditLog,
    KnowledgeChunk,
)
from app.models.base import Base, IdMixin, TimestampMixin, new_id, utcnow
from app.models.change import ChangeImpact, ChangeRequest
from app.models.dict import DictCategory, DictCategoryCode, DictItem
from app.models.document import (
    Document,
    DocumentAccess,
    DocumentRelation,
    DocumentVersion,
    FileObject,
)
from app.models.issue import Issue, IssueAction
from app.models.org import AppUser, Organization, UserOrg
from app.models.project import (
    DesignParam,
    Pile,
    Project,
    ProjectMember,
    ProjectStage,
    SoilLayer,
    SoilProperty,
)
from app.models.workflow import WorkflowInstance, WorkflowTask, WorkflowTemplate

__all__ = [
    "Base",
    "IdMixin",
    "TimestampMixin",
    "new_id",
    "utcnow",
    # 字典
    "DictCategory",
    "DictItem",
    "DictCategoryCode",
    # 组织与用户
    "Organization",
    "AppUser",
    "UserOrg",
    # 项目与专业对象
    "Project",
    "ProjectStage",
    "ProjectMember",
    "SoilLayer",
    "SoilProperty",
    "DesignParam",
    "Pile",
    # 文件与版本
    "FileObject",
    "Document",
    "DocumentVersion",
    "DocumentRelation",
    "DocumentAccess",
    # 流程
    "WorkflowTemplate",
    "WorkflowInstance",
    "WorkflowTask",
    # 变更
    "ChangeRequest",
    "ChangeImpact",
    # 问题
    "Issue",
    "IssueAction",
    # AI 与审计
    "KnowledgeChunk",
    "AIConversation",
    "AIMessage",
    "AICitation",
    "AuditLog",
]
