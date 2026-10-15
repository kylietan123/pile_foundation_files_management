"""Pydantic 数据契约（Schemas）。

这一层是**前后端之间的契约**。前端按这些结构生成 TypeScript 类型，
后端改动字段必须同步通知前端 —— 这是三个人并行开发时的关键约定。

命名规则：
  XxxCreate  创建请求
  XxxUpdate  更新请求（字段全部可选）
  XxxOut     响应体
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import (
    ChangeCategory,
    ChangeState,
    DocumentState,
    ImpactTargetType,
    IssueActionType,
    IssueSource,
    IssueStatus,
    SecretLevel,
    Severity,
    StageCode,
    TaskAction,
    VerifyStatus,
)

T = TypeVar("T")


# ============================================================
# 统一响应包体
#   成功: {"code": 0, "message": "ok", "data": {...}, "trace_id": "uuid"}
#   错误码分段:
#     1000-1999 参数/校验错误
#     2000-2999 认证错误
#     3000-3999 权限错误（须区分"无角色"与"无数据范围"）
#     4000-4999 业务规则错误（如：引用了未发布版本）
#     5000-5999 系统错误
# ============================================================


class ApiResponse(BaseModel, Generic[T]):
    code: int = 0
    message: str = "ok"
    data: T | None = None
    trace_id: str | None = None


class PageMeta(BaseModel):
    page: int
    size: int
    total: int
    pages: int


class PageData(BaseModel, Generic[T]):
    items: list[T]
    meta: PageMeta


# ============================================================
# 认证
# ============================================================


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=128)


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class RefreshRequest(BaseModel):
    refresh_token: str


# ============================================================
# 用户 / 组织 / 权限
# ============================================================


class OrgBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    short_name: str | None = None
    org_type: str
    is_internal: bool = False


class MembershipOut(BaseModel):
    """用户在某个项目上的**参与单位身份**与权限范围。

    阶段范围由《管理流程》矩阵推导，不是单独配的 ——
    所以 `stages` 与 `primary_stages` 是算出来的，不是存出来的。
    """

    project_id: str
    project_name: str | None = None
    unit_code: str
    unit_label: str
    #: 该单位在矩阵里有责任的全部阶段
    stages: list[str] = Field(default_factory=list)
    #: 其中本单位是**主办**（主要责任）的阶段
    primary_stages: list[str] = Field(default_factory=list)
    #: 展示用的责任等级（取所有参与阶段里最重的一级）
    responsibility: str | None = None
    responsibility_label: str | None = None
    actions: list[str] = Field(default_factory=list)


class CurrentUserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    username: str
    name: str
    employee_no: str | None = None
    phone: str | None = None
    email: str | None = None
    title: str | None = None
    is_superuser: bool
    orgs: list[OrgBrief] = Field(default_factory=list)
    memberships: list[MembershipOut] = Field(default_factory=list)


# ============================================================
# 项目
# ============================================================


class StageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    stage_code: str
    stage_label: str | None = None
    status: str
    progress: int = 0
    sort: int = 0
    plan_start: datetime | None = None
    plan_end: datetime | None = None
    actual_start: datetime | None = None
    actual_end: datetime | None = None
    owner_user_id: str | None = None


class ProjectOut(BaseModel):
    """项目列表 / 详情响应。

    `my_*` 字段是**按当前登录人计算出来的** ——
    同一个项目，不同单位的人看到的值不同。这是权限"一份配置全局生效"的体现。

    其中 `my_stages` 与 `my_primary_stages` 由《管理流程》矩阵推导：
    前者是"我在这个项目里能看到哪些阶段"，
    后者是"其中哪些阶段我是主办单位（能上传/发布）"。
    """

    model_config = ConfigDict(from_attributes=True)

    id: str
    project_no: str
    name: str
    short_name: str | None = None
    location: str | None = None
    province: str | None = None
    city: str | None = None
    project_type: str | None = None
    scale_desc: str | None = None

    current_stage_code: str
    current_stage_label: str | None = None
    status: str

    plan_start: datetime | None = None
    plan_end: datetime | None = None
    actual_start: datetime | None = None
    actual_end: datetime | None = None

    # ---- 按当前用户计算 ----
    #: 我在本项目的参与单位（多重身份时取责任最重的那个）
    my_unit: str | None = None
    my_unit_label: str | None = None
    #: 我在本项目的责任等级（主要 / 次要 / 参与）
    my_responsibility: str | None = None
    my_responsibility_label: str | None = None
    #: 我能看到的阶段
    my_stages: list[str] = Field(default_factory=list)
    #: 其中我是主办单位的阶段
    my_primary_stages: list[str] = Field(default_factory=list)

    # ---- 待办统计（可选，列表页用）----
    pending_task_count: int = 0
    overdue_count: int = 0
    open_issue_count: int = 0

    stages: list[StageOut] = Field(default_factory=list)


# ============================================================
# 字典
# ============================================================


class DictItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    category_id: str
    parent_id: str | None = None
    code: str
    name: str
    extra: dict | None = None
    description: str | None = None
    sort: int = 0
    active: bool = True


class DictCategoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    code: str
    name: str
    description: str | None = None
    is_system: bool = False
    sort: int = 0
    items: list[DictItemOut] = Field(default_factory=list)


# ============================================================
# 文件与版本
# ============================================================


class FileObjectOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    file_id: str
    size: int
    mime: str | None = None
    ext: str | None = None
    original_name: str | None = None


class DocumentVersionOut(BaseModel):
    """版本状态机的对外表达。

    available_actions 是**按当前登录人的角色算出来的**，
    前端据此决定显示哪些按钮。真正的拦截仍在后端。
    """

    model_config = ConfigDict(from_attributes=True)

    id: str
    document_id: str
    project_id: str
    version_no: str
    revision: int
    state: DocumentState
    state_label: str | None = None

    change_summary: str | None = None
    remark: str | None = None

    file: FileObjectOut | None = None

    created_by: str | None = None
    created_by_name: str | None = None
    created_at: datetime | None = None
    submitted_at: datetime | None = None
    published_at: datetime | None = None
    published_by: str | None = None

    voided_at: datetime | None = None
    void_reason: str | None = None

    from_change_id: str | None = None
    supersedes_version_id: str | None = None

    # 自校标记：人员不足的例外，前台必须显著标注
    is_self_checked: bool = False
    self_check_reason: str | None = None

    # 流程信息
    workflow_instance_id: str | None = None
    current_node: str | None = None

    available_actions: list[str] = Field(default_factory=list)


class DocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    stage_code: StageCode
    stage_label: str | None = None

    category_id: str | None = None
    category_name: str | None = None
    title: str
    doc_no: str | None = None
    discipline: str = "GENERAL"
    secret_level: str = "INTERNAL"
    secret_level_label: str | None = None

    current_version_id: str | None = None
    published_version_no: str | None = None

    created_by: str | None = None
    created_at: datetime | None = None
    remark: str | None = None

    # 版本摘要
    version_count: int = 0
    latest_version_no: str | None = None
    latest_state: DocumentState | None = None

    versions: list[DocumentVersionOut] = Field(default_factory=list)


class DocumentCreate(BaseModel):
    project_id: str
    stage_code: StageCode
    title: str = Field(min_length=1, max_length=300)
    category_id: str | None = None
    doc_no: str | None = Field(default=None, max_length=100)
    discipline: str = "GENERAL"
    secret_level: SecretLevel = SecretLevel.INTERNAL
    remark: str | None = None


class VersionCreate(BaseModel):
    """上传新版本时随文件一起提交的元信息。"""

    change_summary: str | None = Field(default=None, max_length=2000)
    version_no: str | None = Field(default=None, max_length=32)
    remark: str | None = None


class VersionActionIn(BaseModel):
    """审批动作。"""

    action: TaskAction
    comment: str | None = None
    # 自校开关：模板允许时才生效，且会留痕
    allow_self_check: bool = False


class PublishIn(BaseModel):
    void_reason_for_previous: str | None = None


class RevisionIn(BaseModel):
    reason: str = Field(min_length=1, max_length=2000)


class VoidIn(BaseModel):
    reason: str = Field(min_length=1, max_length=2000)


class DownloadTokenOut(BaseModel):
    file_id: str
    version_id: str
    expires_at: int
    ttl_seconds: int
    url: str


class WorkflowTaskOut(BaseModel):
    """审批任务。历轮退回的记录都保留，形成完整审批轨迹。"""

    model_config = ConfigDict(from_attributes=True)

    id: str
    instance_id: str
    project_id: str
    node_code: str
    node_name: str | None = None
    round: int
    assignee: str | None = None
    assignee_name: str | None = None
    assignee_role: str | None = None
    action: TaskAction | None = None
    comment: str | None = None
    due_at: datetime | None = None
    acted_at: datetime | None = None
    acted_by: str | None = None
    is_self_check: bool = False


class WorkflowTraceOut(BaseModel):
    """审批轨迹。用于"这份图纸被退回过几次、每次谁说了什么"。"""

    instance_id: str
    biz_type: str
    status: str
    current_node: str | None = None
    round: int = 1
    initiator: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    tasks: list[WorkflowTaskOut] = Field(default_factory=list)


# ============================================================
# 设计输入（参数溯源）
# ============================================================


class ParamSourceOut(BaseModel):
    """参数来源详情 —— 点开"来源"看这个。

    这是"每个参数可回溯到勘察报告页码"的实现。
    """

    version_id: str
    version_no: str
    state: DocumentState
    document_id: str
    document_title: str | None = None
    doc_no: str | None = None
    category_name: str | None = None
    locator: str | None = None
    has_newer_published: bool = False
    latest_version_no: str | None = None
    latest_version_id: str | None = None


class DesignParamOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    stage_code: StageCode | None = None

    param_code: str
    param_name: str
    param_group: str | None = None

    value_num: float | None = None
    value_text: str | None = None
    unit: str | None = None
    display_value: str | None = None

    source_type: str | None = None
    source_version_id: str | None = None
    source_locator: str | None = None
    source: ParamSourceOut | None = None

    verify_status: VerifyStatus
    verify_status_label: str | None = None
    required: bool = False
    verified_by: str | None = None
    verified_by_name: str | None = None
    verified_at: datetime | None = None
    verify_note: str | None = None

    locked: bool = False
    locked_at: datetime | None = None


class DesignParamVerifyIn(BaseModel):
    """核验动作。"""

    action: str = Field(description="verify / modify / doubtful / pending")
    new_value_num: float | None = None
    new_value_text: str | None = None
    note: str | None = None


class DesignInputSummaryOut(BaseModel):
    total: int = 0
    required_total: int = 0
    verified: int = 0
    pending: int = 0
    doubtful: int = 0
    stale: int = 0
    modified: int = 0
    by_status: dict[str, int] = Field(default_factory=dict)
    unverified_required_count: int = 0
    unverified_required: list[dict] = Field(default_factory=list)
    locked: bool = False
    locked_count: int = 0
    can_lock: bool = False


class LockInputsIn(BaseModel):
    reason: str | None = None


class UnlockInputsIn(BaseModel):
    reason: str = Field(min_length=1)


class RelinkSourceIn(BaseModel):
    new_version_id: str


class StaleRefreshOut(BaseModel):
    stale_count: int = 0
    affected: list[dict] = Field(default_factory=list)


# ============================================================
# 设计变更与影响分析
# ============================================================


class ImpactOut(BaseModel):
    """变更影响明细。

    requires_immediate_notice=True 表示涉及已施工部位 —— 最高风险，需立即通知。
    """

    model_config = ConfigDict(from_attributes=True)

    id: str
    change_id: str
    target_type: ImpactTargetType
    target_type_label: str | None = None
    target_id: str | None = None
    target_name: str | None = None
    impact_desc: str
    severity: str = "NORMAL"
    requires_immediate_notice: bool = False
    handled: bool = False
    handled_by: str | None = None
    handled_by_name: str | None = None
    handled_at: datetime | None = None
    handle_note: str | None = None


class ChangeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    stage_code: StageCode
    stage_label: str | None = None

    change_no: str
    title: str
    category: ChangeCategory | None = None
    category_label: str | None = None
    reason: str
    description: str | None = None

    state: ChangeState
    state_label: str | None = None

    origin_version_id: str | None = None
    new_version_id: str | None = None

    impact_pile_count: int = 0
    impact_constructed_count: int = 0
    impact_cost_delta: float | None = None
    impact_schedule_days: int | None = None
    impact_scope: dict | None = None

    initiator: str | None = None
    initiator_name: str | None = None
    approver: str | None = None

    workflow_instance_id: str | None = None
    current_node: str | None = None

    submitted_at: datetime | None = None
    approved_at: datetime | None = None
    closed_at: datetime | None = None
    created_at: datetime | None = None

    impacts: list[ImpactOut] = Field(default_factory=list)

    # 按当前登录人算出的可用动作
    available_actions: list[str] = Field(default_factory=list)
    # 影响处理进度
    impact_total: int = 0
    impact_handled: int = 0
    # 是否涉及已施工部位（前端显著标红）
    has_constructed_impact: bool = False


class ChangeCreateIn(BaseModel):
    stage_code: StageCode = StageCode.DESIGN
    title: str = Field(min_length=1, max_length=300)
    category: ChangeCategory
    reason: str = Field(min_length=1, max_length=4000)
    description: str | None = None
    origin_version_id: str | None = None
    change_no: str | None = Field(default=None, max_length=64)


class ImpactAnalyzeIn(BaseModel):
    """执行影响分析时的范围参数。

    scope_zones        按分区筛选（如 ["1#楼"]）
    affected_pile_ids  直接指定受影响桩位
    两者都不传时只做文档级影响分析（不逐桩）。
    """

    scope_zones: list[str] | None = None
    affected_pile_ids: list[str] | None = None


class ImpactHandleIn(BaseModel):
    note: str = Field(min_length=1, max_length=2000)


class ChangeApproveIn(BaseModel):
    action: TaskAction
    comment: str | None = None
    allow_self_check: bool = False


class AffectedPileOut(BaseModel):
    """受影响桩位（分析结果的可视化辅助）。"""

    model_config = ConfigDict(from_attributes=True)

    id: str
    pile_no: str
    zone: str | None = None
    pile_type_name: str | None = None
    design_length: float | None = None
    design_capacity: float | None = None
    status: str
    constructed_at: date | None = None


# ============================================================
# 问题管理与闭环
# ============================================================


class IssueActionOut(BaseModel):
    """处理记录。八段式链路的每一步都在这里留痕。"""

    id: str
    action_type: IssueActionType
    action_label: str | None = None
    sequence: int = 0
    content: str
    is_ai_generated: bool = False
    ai_citation: str | None = None
    actor: str | None = None
    actor_name: str | None = None
    acted_at: datetime | None = None
    attachment_version_id: str | None = None
    sort: int = 0


class IssueOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    stage_code: StageCode
    stage_label: str | None = None

    issue_no: str | None = None
    title: str
    description: str

    source: IssueSource
    source_label: str | None = None
    issue_type_id: str | None = None
    issue_type_name: str | None = None

    severity: Severity
    severity_label: str | None = None
    status: IssueStatus
    status_label: str | None = None

    related_pile_id: str | None = None
    related_version_id: str | None = None
    related_change_id: str | None = None

    raise_by: str | None = None
    raise_by_name: str | None = None
    raise_at: datetime | None = None
    assignee: str | None = None
    assignee_name: str | None = None
    due_date: date | None = None
    overdue: bool = False

    verified_by: str | None = None
    verified_at: datetime | None = None
    verify_conclusion: str | None = None

    closed_at: datetime | None = None
    closed_by: str | None = None

    is_knowledge: bool = False
    knowledge_summary: str | None = None

    actions: list[IssueActionOut] = Field(default_factory=list)
    available_actions: list[str] = Field(default_factory=list)
    completed_steps: int = 0
    total_steps: int = 8


class IssueCreateIn(BaseModel):
    stage_code: StageCode = StageCode.DESIGN
    title: str = Field(min_length=1, max_length=300)
    description: str = Field(min_length=1, max_length=4000)
    source: IssueSource = IssueSource.REVIEW
    issue_type_id: str | None = None
    severity: Severity = Severity.NORMAL
    related_pile_id: str | None = None
    related_version_id: str | None = None
    related_change_id: str | None = None
    assignee: str | None = None
    due_date: date | None = None


class IssueActionIn(BaseModel):
    """追加一条处理记录。

    action_type 必须是八段式链路的下一步（不可跳步）。
    """

    action_type: IssueActionType
    content: str = Field(min_length=1, max_length=4000)
    is_ai_generated: bool = False
    ai_citation: str | None = None
    attachment_version_id: str | None = None


class IssueSummaryOut(BaseModel):
    total: int = 0
    open: int = 0
    in_progress: int = 0
    pending_verify: int = 0
    closed: int = 0
    escalated: int = 0
    high: int = 0
    overdue_count: int = 0
    overdue_issues: list[dict] = Field(default_factory=list)
    unclosed: int = 0
    knowledge_count: int = 0
    by_status: dict[str, int] = Field(default_factory=dict)
    by_source: dict[str, int] = Field(default_factory=dict)


class KnowledgeConsolidateIn(BaseModel):
    """知识沉淀。summary 不传则用闭环时自动生成的摘要。"""

    summary: str | None = None


class KnowledgeItemOut(BaseModel):
    """知识条目（供 AI 检索与人工查阅）。"""

    model_config = ConfigDict(from_attributes=True)

    issue_id: str
    issue_no: str | None = None
    title: str
    stage_code: StageCode | None = None
    stage_label: str | None = None
    severity: Severity | None = None
    knowledge_summary: str | None = None
    closed_at: datetime | None = None
    project_id: str | None = None
    project_name: str | None = None


# ============================================================
# 设计成果与交付完整性
# ============================================================


class DeliverableOut(BaseModel):
    """单项成果的状态。

    ready=False 时会给出 blockers —— 让用户知道**为什么不能交付**，
    而不是只看到一个红色标记。
    """

    type_code: str
    type_name: str
    required: bool = False
    note: str | None = None

    exists: bool = False
    document_id: str | None = None
    document_title: str | None = None
    doc_no: str | None = None

    current_version_no: str | None = None
    current_version_state: str | None = None
    has_unpublished_newer: bool = False
    latest_version_no: str | None = None
    latest_version_state: str | None = None
    version_count: int = 0

    ready: bool = False
    blockers: list[str] = Field(default_factory=list)
    extra_documents: list[dict] = Field(default_factory=list)


class DeliveryGateOut(BaseModel):
    """交付关卡。六道全过才允许交付。"""

    gate: int
    code: str
    name: str
    passed: bool
    detail: str | None = None
    blockers: list[str] = Field(default_factory=list)
    suggestion: str | None = None


class DeliveryCheckOut(BaseModel):
    """交付完整性检查结果。

    **每一关都给出人话的原因和可操作的建议** ——
    只说"检查不通过"，用户不知道该怎么办。
    """

    can_deliver: bool = False
    stage_code: StageCode
    checked_at: str | None = None
    gates: list[DeliveryGateOut] = Field(default_factory=list)
    failed_gate_count: int = 0
    blocker_count: int = 0
    summary: str | None = None


class ManifestItemOut(BaseModel):
    type_name: str
    document_id: str | None = None
    title: str | None = None
    doc_no: str | None = None
    version_no: str | None = None
    published_at: datetime | None = None
    is_self_checked: bool = False
    file_name: str | None = None


class ManifestOut(BaseModel):
    """交付清单。只收录已发布版本的成果。"""

    project_id: str
    stage_code: StageCode
    generated_at: str | None = None
    item_count: int = 0
    items: list[ManifestItemOut] = Field(default_factory=list)
    note: str | None = None


# ============================================================
# AI 问答
# ============================================================


class AIAskIn(BaseModel):
    """提问。

    会话强制绑定项目 —— 内部试用期不允许跨项目检索。
    """

    question: str = Field(min_length=1, max_length=2000)
    conversation_id: str | None = None
    stage_code: StageCode | None = None
    discipline: str | None = None
    # 是否把跨项目知识库（已沉淀的通用经验）纳入检索
    include_knowledge_base: bool = True


class AICitationOut(BaseModel):
    """引用。**没有引用的回答不允许展示给用户。**"""

    id: str | None = None
    chunk_id: str | None = None
    source_type: str | None = None
    source_version_id: str | None = None
    document_id: str | None = None
    document_title: str | None = None
    doc_no: str | None = None
    version_no: str | None = None
    section_path: str | None = None
    page_no: int | None = None
    # 人话定位串，如「详勘 V2.0 第4章 P.15」
    locator: str | None = None
    quoted_text: str | None = None
    score: float | None = None


class AIAnswerOut(BaseModel):
    """四段式回答。

    `has_citation=False` 时前端**不应展示**该回答 —— 这是治理规则。
    `degraded=True` 表示未配置模型，此时只返回检索到的原文，不生成归纳。
    """

    conversation_id: str
    message_id: str
    question: str

    content: str
    conclusion: str | None = None
    basis: str | None = None
    uncertainty: str | None = None
    disclaimer: str | None = None
    is_complete: bool = False

    has_citation: bool = False
    citations: list[AICitationOut] = Field(default_factory=list)

    degraded: bool = False
    degrade_reason: str | None = None
    provider: str | None = None
    model: str | None = None
    latency_ms: int | None = None


class AIMessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    role: str
    content: str
    conclusion: str | None = None
    uncertainty: str | None = None
    disclaimer: str | None = None
    has_citation: bool = False
    model: str | None = None
    provider: str | None = None
    latency_ms: int | None = None
    error: str | None = None
    feedback: str | None = None
    feedback_note: str | None = None
    created_at: datetime | None = None
    citations: list[AICitationOut] = Field(default_factory=list)


class AIConversationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    stage_code: StageCode | None = None
    title: str | None = None
    message_count: int = 0
    created_at: datetime | None = None
    updated_at: datetime | None = None


class AIProviderStatusOut(BaseModel):
    """提供方状态。前端据此显示"AI 未配置"提示。"""

    mode: str
    available: bool
    model: str | None = None
    base_url_configured: bool = False
    allow_cross_project: bool = False
    log_retention_days: int = 90
    note: str | None = None


class AIFeedbackIn(BaseModel):
    feedback: str = Field(description="USEFUL / USELESS")
    note: str | None = None


class KnowledgeIndexIn(BaseModel):
    """把已发布版本切片入知识库。"""

    version_id: str


# ============================================================
# 文档台账与追溯
# ============================================================


class ActorBrief(BaseModel):
    """操作人 —— **姓名 + 工号**。用户要求"谁做的要看得见"。"""

    id: str
    name: str | None = None
    employee_no: str | None = None


class LedgerTraceItem(BaseModel):
    """一次签认记录。"""

    node_code: str
    node_name: str | None = None
    unit_code: str | None = None
    unit_label: str | None = None
    action: str | None = None
    comment: str | None = None
    actor: ActorBrief | None = None
    acted_at: datetime | None = None
    round: int = 1


class LedgerItem(BaseModel):
    """台账的一行。

    回答三个问题：文件是什么、**谁做的**、**现在在谁手上**。
    `primary_unit` 是文件丢了要找的那个单位。
    """

    document_id: str
    doc_no: str | None = None
    title: str
    category_name: str | None = None
    stage_code: str | None = None
    stage_label: str | None = None
    discipline: str | None = None
    secret_level: str | None = None

    #: 这份文件"当前该看的状态"：在途优先 → 已发布 → 最新
    effective_version_no: str | None = None
    effective_state: str | None = None
    effective_state_label: str | None = None
    #: 当前已发布版本（未发布过则为空）
    current_version_no: str | None = None
    current_state: str | None = None
    current_state_label: str | None = None
    latest_version_no: str | None = None
    latest_state: str | None = None
    version_count: int = 0

    primary_unit: str | None = None
    primary_unit_label: str | None = None

    created_by: ActorBrief | None = None
    current_uploaded_by: ActorBrief | None = None
    current_uploaded_at: datetime | None = None
    published_by: ActorBrief | None = None
    published_at: datetime | None = None

    inflight_version_no: str | None = None
    pending_units: list[str] = Field(default_factory=list)
    pending_unit_labels: list[str] = Field(default_factory=list)
    #: 待签任务数（0 且未发布 = 还没提交；>0 = 提交了在等人签）
    pending_count: int = 0
    waits_on: str | None = None
    awaiting_me: bool = False
    workflow_finished: bool = False

    trace: list[LedgerTraceItem] = Field(default_factory=list)


class LedgerOut(BaseModel):
    """项目文档台账。"""

    project_id: str
    stage_code: str | None = None
    generated_at: str | None = None
    item_count: int = 0
    awaiting_count: int = 0
    items: list[LedgerItem] = Field(default_factory=list)


class StageResponsibilityDetail(BaseModel):
    unit_code: str
    unit_label: str | None = None
    responsibility: str
    responsibility_label: str | None = None


class StageResponsibilityOut(BaseModel):
    """某阶段的"谁负责 + 有多少文件卡在签认"。"""

    stage_code: str
    stage_label: str | None = None
    primary_unit: str | None = None
    inaround_count: int = 0
    units_detail: list[StageResponsibilityDetail] = Field(default_factory=list)


# ============================================================
# 工作台（跨项目交办事项）
# ============================================================


class WorkItem(BaseModel):
    """一条交办事项。

    kind 区分三类：AWAITING_ME / RETURNED_TO_ME / INFLIGHT。
    """

    kind: str
    task_id: str | None = None
    project_id: str
    project_name: str | None = None
    project_short_name: str | None = None
    stage_code: str | None = None
    node_code: str | None = None
    node_name: str | None = None
    my_unit: str | None = None
    my_unit_label: str | None = None

    document_id: str | None = None
    doc_no: str | None = None
    title: str | None = None
    version_no: str | None = None
    version_state: str | None = None
    version_state_label: str | None = None

    submitted_by: str | None = None
    submitted_by_no: str | None = None
    submitted_at: datetime | None = None

    due_at: datetime | None = None
    days_left: int | None = None
    overdue: bool = False
    round: int | None = None

    pending_units: list[str] = Field(default_factory=list)
    pending_unit_labels: list[str] = Field(default_factory=list)


class StageWorkBucket(BaseModel):
    """按阶段聚合的交办事项。"""

    stage_code: str
    stage_label: str | None = None
    awaiting: list[WorkItem] = Field(default_factory=list)
    returned: list[WorkItem] = Field(default_factory=list)


class WorkbenchOut(BaseModel):
    """我的工作 / 项目交办事项。"""

    user_id: str | None = None
    project_id: str | None = None
    generated_at: str | None = None
    awaiting_count: int = 0
    returned_count: int = 0
    inflight_count: int = 0
    overdue_count: int = 0
    awaiting: list[WorkItem] = Field(default_factory=list)
    returned: list[WorkItem] = Field(default_factory=list)
    inflight: list[WorkItem] = Field(default_factory=list)
    by_stage: list[StageWorkBucket] = Field(default_factory=list)
