/**
 * 接口契约类型。
 *
 * ⚠️ 本文件必须与 backend/app/schemas.py 和 backend/app/models/enums.py 保持一致。
 * 后端改字段必须同步改这里，并通知前端 —— 这是三人并行开发的关键约定。
 */

// ============================================================
// 统一响应包体
// ============================================================

export interface ApiResponse<T> {
  code: number
  message: string
  data: T | null
  trace_id?: string | null
}

export interface PageMeta {
  page: number
  size: number
  total: number
  pages: number
}

export interface PageData<T> {
  items: T[]
  meta: PageMeta
}

/** 后端错误码分段 */
export const ApiCode = {
  OK: 0,
  // 1000-1999 参数/校验错误
  VALIDATION_FAILED: 1001,
  // 2000-2999 认证错误
  UNAUTHORIZED: 2001,
  TOKEN_EXPIRED: 2002,
  USER_DISABLED: 2003,
  // 3000-3999 权限错误
  NO_ROLE: 3001,
  NO_DATA_SCOPE: 3002,
  STAGE_DENIED: 3003,
  // 4000-4999 业务规则错误
  VERSION_NOT_PUBLISHED: 4001,
  // 5000-5999 系统错误
  SERVER_ERROR: 5000,
} as const

// ============================================================
// 枚举（与后端 models/enums.py 对应）
// ============================================================

/** 7 个阶段。跨阶段数据互通的根本。 */
export const StageCode = {
  PRE_SURVEY: 'PRE_SURVEY',
  INVESTIGATION: 'INVESTIGATION',
  DESIGN_TEST_PILE: 'DESIGN_TEST_PILE',
  DESIGN: 'DESIGN',
  CONSTRUCTION: 'CONSTRUCTION',
  ACCEPT_TEST_PILE: 'ACCEPT_TEST_PILE',
  MONITORING: 'MONITORING',
} as const
export type StageCode = (typeof StageCode)[keyof typeof StageCode]

export const STAGE_LABEL: Record<StageCode, string> = {
  PRE_SURVEY: '前期调研',
  INVESTIGATION: '勘察',
  DESIGN_TEST_PILE: '设计试桩',
  DESIGN: '设计',
  CONSTRUCTION: '施工',
  ACCEPT_TEST_PILE: '验收试桩',
  MONITORING: '运维监测',
}

export const STAGE_ORDER: StageCode[] = [
  StageCode.PRE_SURVEY,
  StageCode.INVESTIGATION,
  StageCode.DESIGN_TEST_PILE,
  StageCode.DESIGN,
  StageCode.CONSTRUCTION,
  StageCode.ACCEPT_TEST_PILE,
  StageCode.MONITORING,
]

export const StageStatus = {
  NOT_STARTED: 'NOT_STARTED',
  IN_PROGRESS: 'IN_PROGRESS',
  COMPLETED: 'COMPLETED',
  SUSPENDED: 'SUSPENDED',
} as const
export type StageStatus = (typeof StageStatus)[keyof typeof StageStatus]

export const ProjectStatus = {
  PREPARING: 'PREPARING',
  IN_PROGRESS: 'IN_PROGRESS',
  SUSPENDED: 'SUSPENDED',
  COMPLETED: 'COMPLETED',
  ARCHIVED: 'ARCHIVED',
} as const
export type ProjectStatus = (typeof ProjectStatus)[keyof typeof ProjectStatus]

export const PROJECT_STATUS_LABEL: Record<ProjectStatus, string> = {
  PREPARING: '筹备',
  IN_PROGRESS: '进行中',
  SUSPENDED: '暂停',
  COMPLETED: '已完成',
  ARCHIVED: '已归档',
}

/**
 * 参与单位 —— 全平台权限主体。
 *
 * 注意：主体是**单位**，不是"设计人/校核人"这类岗位。
 * 单位内部的经办人由各单位自行指定，系统只保证每次操作都留下操作人。
 */
export const UnitCode = {
  OWNER: 'OWNER',
  SURVEYOR: 'SURVEYOR',
  DESIGN_TEST_PILE: 'DESIGN_TEST_PILE',
  DESIGNER: 'DESIGNER',
  GENERAL_CONTRACTOR: 'GENERAL_CONTRACTOR',
  SUBCONTRACTOR: 'SUBCONTRACTOR',
  SUPERVISOR: 'SUPERVISOR',
  ACCEPT_TEST_PILE: 'ACCEPT_TEST_PILE',
  INSPECTOR: 'INSPECTOR',
  GOVERNMENT: 'GOVERNMENT',
  ADMIN: 'ADMIN',
} as const
export type UnitCode = (typeof UnitCode)[keyof typeof UnitCode]

export const UNIT_LABEL: Record<UnitCode, string> = {
  OWNER: '建设单位',
  SURVEYOR: '勘察单位',
  DESIGN_TEST_PILE: '设计试桩单位',
  DESIGNER: '设计单位',
  GENERAL_CONTRACTOR: '总包单位',
  SUBCONTRACTOR: '分包单位',
  SUPERVISOR: '监理单位',
  ACCEPT_TEST_PILE: '验收试桩单位',
  INSPECTOR: '检测监测单位',
  GOVERNMENT: '政府审查单位',
  ADMIN: '系统管理员',
}

/** 责任等级 —— 由《管理流程》矩阵定义，直接决定权限 */
export const Responsibility = {
  PRIMARY: 'PRIMARY',
  RELATED: 'RELATED',
  PARTICIPANT: 'PARTICIPANT',
  VERIFIER: 'VERIFIER',
} as const
export type Responsibility = (typeof Responsibility)[keyof typeof Responsibility]

export const RESPONSIBILITY_LABEL: Record<Responsibility, string> = {
  PRIMARY: '主要责任',
  RELATED: '次要责任',
  PARTICIPANT: '参与',
  VERIFIER: '审查',
}

/** 责任等级对应的标签色（主办醒目、参与淡） */
export const RESPONSIBILITY_TAG: Record<Responsibility, string> = {
  PRIMARY: 'danger',
  RELATED: 'warning',
  PARTICIPANT: 'info',
  VERIFIER: 'primary',
}

/** 权限动作 —— 由责任等级推导，不是单独配的 */
export const PermissionAction = {
  VIEW: 'VIEW',
  DOWNLOAD: 'DOWNLOAD',
  EDIT: 'EDIT',
  SUBMIT: 'SUBMIT',
  PUBLISH: 'PUBLISH',
  CONFIRM: 'CONFIRM',
  COMMENT: 'COMMENT',
} as const
export type PermissionAction = (typeof PermissionAction)[keyof typeof PermissionAction]

/** 文件版本状态机 */
export const DocumentState = {
  DRAFT: 'DRAFT',
  CHECKING: 'CHECKING',
  REVIEWING: 'REVIEWING',
  APPROVED: 'APPROVED',
  REVISING: 'REVISING',
  PUBLISHED: 'PUBLISHED',
  VOID: 'VOID',
} as const
export type DocumentState = (typeof DocumentState)[keyof typeof DocumentState]

export const DOCUMENT_STATE_LABEL: Record<DocumentState, string> = {
  DRAFT: '草稿',
  CHECKING: '校核中',
  REVIEWING: '审核中',
  APPROVED: '已批准',
  REVISING: '修订中',
  PUBLISHED: '已发布',
  VOID: '已作废',
}

/** Element Plus tag 类型映射，避免在模板里散落 if-else */
export const DOCUMENT_STATE_TAG: Record<DocumentState, 'success' | 'info' | 'warning' | 'danger' | 'primary'> = {
  DRAFT: 'info',
  CHECKING: 'warning',
  REVIEWING: 'warning',
  APPROVED: 'primary',
  REVISING: 'warning',
  PUBLISHED: 'success',
  VOID: 'danger',
}

// ============================================================
// 认证
// ============================================================

export interface LoginRequest {
  username: string
  password: string
}

export interface TokenPair {
  access_token: string
  refresh_token: string
  token_type: string
  expires_in: number
}

export interface OrgBrief {
  id: string
  name: string
  short_name?: string | null
  org_type: string
  is_internal: boolean
}

export interface Membership {
  project_id: string
  project_name?: string | null
  unit_code: UnitCode
  unit_label: string
  /** 该单位在《管理流程》矩阵里有责任的全部阶段（由矩阵推导） */
  stages: StageCode[]
  /** 其中本单位是**主办**（主要责任）的阶段 —— 能上传/发布 */
  primary_stages: StageCode[]
  /** 展示用的责任等级（取所有参与阶段里最重的一级） */
  responsibility?: Responsibility | null
  responsibility_label?: string | null
  actions: PermissionAction[]
}

export interface CurrentUser {
  id: string
  username: string
  name: string
  employee_no?: string | null
  phone?: string | null
  email?: string | null
  title?: string | null
  is_superuser: boolean
  orgs: OrgBrief[]
  memberships: Membership[]
}

// ============================================================
// 项目与阶段
// ============================================================

export interface StageInfo {
  id: string
  stage_code: StageCode
  stage_label?: string | null
  status: StageStatus
  progress: number
  sort: number
  plan_start?: string | null
  plan_end?: string | null
  actual_start?: string | null
  actual_end?: string | null
  owner_user_id?: string | null
}

export interface ProjectCreateIn {
  name: string
  short_name?: string | null
  location?: string | null
  province?: string | null
  city?: string | null
  project_type?: string | null
  scale_desc?: string | null
  description?: string | null
}

export type ProjectUpdateIn = Partial<ProjectCreateIn>

export interface CatalogDocument {
  source_seq: number
  doc_code: string
  phase_name: string
  phase_order: number
  stage_code: StageCode
  stage_label: string
  responsible_unit_code: string
  responsible_unit_name: string
  doc_name: string
  file_formats: string
  is_required: boolean
  need_approval: boolean
  description?: string | null
}

export interface ProjectInfo {
  id: string
  project_no: string
  name: string
  short_name?: string | null
  location?: string | null
  province?: string | null
  city?: string | null
  project_type?: string | null
  scale_desc?: string | null

  current_stage_code: StageCode
  current_stage_label?: string | null
  status: ProjectStatus

  plan_start?: string | null
  plan_end?: string | null
  actual_start?: string | null
  actual_end?: string | null

  /**
   * 我在本项目的参与身份 —— 按当前登录人计算，同一项目不同单位看到的值不同。
   * 多重身份时取责任最重的那一个；完整身份列表在 /auth/me 的 memberships。
   */
  my_unit?: UnitCode | null
  my_unit_label?: string | null
  my_responsibility?: Responsibility | null
  my_responsibility_label?: string | null
  /** 我能看到的阶段（由矩阵推导） */
  my_stages: StageCode[]
  /** 其中我是主办单位的阶段 —— 能上传/发布 */
  my_primary_stages: StageCode[]

  pending_task_count: number
  overdue_count: number
  open_issue_count: number

  stages: StageInfo[]
}

export interface ProjectMemberInfo {
  member_id: string
  user_id: string
  user_name?: string | null
  employee_no?: string | null
  org_id?: string | null
  org_name?: string | null
  unit_code: UnitCode
  unit_label: string
  /** 该单位有责任的阶段 */
  stages: StageCode[]
  /** 其中是主办的阶段（主要责任） */
  primary_stages: StageCode[]
  /** 其中是相关的阶段（次要责任，含政府审查） */
  related_stages?: StageCode[]
  responsibility?: Responsibility | null
  responsibility_label?: string | null
  data_scope?: string | null
  valid_from?: string | null
  valid_to?: string | null
}

// ============================================================
// 字典
// ============================================================

export interface DictItem {
  id: string
  category_id: string
  parent_id?: string | null
  code: string
  name: string
  extra?: Record<string, unknown> | null
  description?: string | null
  sort: number
  active: boolean
}

export interface DictCategory {
  id: string
  code: string
  name: string
  description?: string | null
  is_system: boolean
  sort: number
  items: DictItem[]
}

export interface StageOption {
  code: StageCode
  label: string
  sort: number
}

// ============================================================
// 设计输入（参数溯源）
// ============================================================

export const VerifyStatus = {
  PENDING: 'PENDING',
  VERIFIED: 'VERIFIED',
  MODIFIED: 'MODIFIED',
  DOUBTFUL: 'DOUBTFUL',
  STALE: 'STALE',
} as const
export type VerifyStatus = (typeof VerifyStatus)[keyof typeof VerifyStatus]

export const VERIFY_STATUS_LABEL: Record<VerifyStatus, string> = {
  PENDING: '待核验',
  VERIFIED: '已核验',
  MODIFIED: '已修改',
  DOUBTFUL: '存疑',
  STALE: '来源已失效',
}

export const VERIFY_STATUS_TAG: Record<
  VerifyStatus,
  'success' | 'info' | 'warning' | 'danger' | 'primary'
> = {
  PENDING: 'info',
  VERIFIED: 'success',
  MODIFIED: 'primary',
  DOUBTFUL: 'warning',
  STALE: 'danger',
}

/** 参数来源详情 —— 点开"来源"看到的东西 */
export interface ParamSource {
  version_id: string
  version_no: string
  state: DocumentState
  document_id: string
  document_title?: string | null
  doc_no?: string | null
  category_name?: string | null
  locator?: string | null
  /** 该来源是否已有更新版本 —— STALE 判定的依据 */
  has_newer_published: boolean
  latest_version_no?: string | null
  latest_version_id?: string | null
}

export interface DesignParam {
  id: string
  project_id: string
  stage_code?: StageCode | null
  param_code: string
  param_name: string
  param_group?: string | null
  value_num?: number | null
  value_text?: string | null
  unit?: string | null
  display_value?: string | null
  source_type?: string | null
  source_version_id?: string | null
  source_locator?: string | null
  source?: ParamSource | null
  verify_status: VerifyStatus
  verify_status_label?: string | null
  required: boolean
  verified_by?: string | null
  verified_by_name?: string | null
  verified_at?: string | null
  verify_note?: string | null
  locked: boolean
  locked_at?: string | null
}

export interface DesignInputSummary {
  total: number
  required_total: number
  verified: number
  pending: number
  doubtful: number
  stale: number
  modified: number
  by_status: Record<string, number>
  unverified_required_count: number
  unverified_required: { param_code: string; param_name: string; status: VerifyStatus }[]
  locked: boolean
  locked_count: number
  can_lock: boolean
}

export interface RelinkSourceIn {
  new_version_id: string
}

export interface StaleRefreshResult {
  stale_count: number
  affected: {
    param_id: string
    param_code: string
    param_name: string
    from_version: string
    to_version: string
    locator?: string | null
  }[]
}

// ============================================================
// 文件与版本
// ============================================================

export interface FileObjectInfo {
  file_id: string
  size: number
  mime?: string | null
  ext?: string | null
  original_name?: string | null
}

/** 版本可用动作。按当前登录人算出来，前端据此显示按钮。 */
export type VersionAction = 'submit' | 'approve' | 'return' | 'publish' | 'revise' | 'void' | 'download'

export interface DocumentVersionInfo {
  id: string
  document_id: string
  project_id: string
  version_no: string
  revision: number
  state: DocumentState
  state_label?: string | null
  change_summary?: string | null
  remark?: string | null
  file?: FileObjectInfo | null
  created_by?: string | null
  created_by_name?: string | null
  created_at?: string | null
  submitted_at?: string | null
  published_at?: string | null
  published_by?: string | null
  voided_at?: string | null
  void_reason?: string | null
  from_change_id?: string | null
  supersedes_version_id?: string | null
  /** 自校标记：人员不足的例外，必须显著标注 */
  is_self_checked: boolean
  self_check_reason?: string | null
  workflow_instance_id?: string | null
  current_node?: string | null
  available_actions: VersionAction[]
}

export interface DocumentInfo {
  id: string
  project_id: string
  stage_code: StageCode
  stage_label?: string | null
  category_id?: string | null
  category_name?: string | null
  title: string
  doc_no?: string | null
  discipline: string
  secret_level: string
  secret_level_label?: string | null
  current_version_id?: string | null
  published_version_no?: string | null
  created_by?: string | null
  created_at?: string | null
  remark?: string | null
  version_count: number
  latest_version_no?: string | null
  latest_state?: DocumentState | null
  versions: DocumentVersionInfo[]
}

export interface DocumentCreateIn {
  project_id: string
  stage_code: StageCode
  title: string
  category_id?: string | null
  doc_no?: string | null
  discipline?: string
  secret_level?: string
  remark?: string | null
}

export const SECRET_LEVEL_LABEL: Record<string, string> = {
  PUBLIC: '公开',
  INTERNAL: '内部',
  RESTRICTED: '受限',
  SECRET: '保密',
}

// ============================================================
// 工作流待办
// ============================================================

export interface WorkflowTaskInfo {
  id: string
  instance_id: string
  project_id: string
  node_code: string
  node_name?: string | null
  round: number
  assignee?: string | null
  assignee_name?: string | null
  assignee_role?: string | null
  action?: 'APPROVE' | 'RETURN' | 'REJECT' | null
  comment?: string | null
  due_at?: string | null
  acted_at?: string | null
  acted_by?: string | null
  is_self_check: boolean
}

/** 待办（跨项目聚合时带上下文） */
export interface MyTaskInfo extends WorkflowTaskInfo {
  biz_title?: string | null
  project_name?: string | null
  project_short_name?: string | null
  stage_code?: StageCode | null
  stage_label?: string | null
  overdue: boolean
  biz_type?: string | null
  biz_id?: string | null
}

export interface WorkflowTrace {
  instance_id: string
  biz_type: string
  status: string
  current_node?: string | null
  round: number
  initiator?: string | null
  started_at?: string | null
  finished_at?: string | null
  tasks: WorkflowTaskInfo[]
}

export const NODE_LABEL: Record<string, string> = {
  CHECK: '校核',
  REVIEW: '审核',
  APPROVE: '批准',
  PUBLISH: '发布',
  SELF_CHECK: '自校',
  IMPACT: '影响分析',
}

export const TASK_ACTION_LABEL: Record<string, string> = {
  APPROVE: '通过',
  RETURN: '退回修改',
  REJECT: '驳回',
}

// ============================================================
// 设计变更与影响分析
// ============================================================

export const ChangeState = {
  DRAFT: 'DRAFT',
  IMPACT_ANALYZING: 'IMPACT_ANALYZING',
  PENDING_APPROVAL: 'PENDING_APPROVAL',
  APPROVING: 'APPROVING',
  APPROVED: 'APPROVED',
  REJECTED: 'REJECTED',
  EXECUTING: 'EXECUTING',
  CLOSED: 'CLOSED',
} as const
export type ChangeState = (typeof ChangeState)[keyof typeof ChangeState]

export const CHANGE_STATE_LABEL: Record<ChangeState, string> = {
  DRAFT: '待提交',
  IMPACT_ANALYZING: '影响分析中',
  PENDING_APPROVAL: '待审批',
  APPROVING: '审批中',
  APPROVED: '已批准',
  REJECTED: '已驳回',
  EXECUTING: '执行中',
  CLOSED: '已关闭',
}

export const CHANGE_STATE_TAG: Record<
  ChangeState,
  'success' | 'info' | 'warning' | 'danger' | 'primary'
> = {
  DRAFT: 'info',
  IMPACT_ANALYZING: 'warning',
  PENDING_APPROVAL: 'warning',
  APPROVING: 'warning',
  APPROVED: 'primary',
  REJECTED: 'danger',
  EXECUTING: 'primary',
  CLOSED: 'success',
}

export const ChangeCategory = {
  SURVEY_DATA: 'SURVEY_DATA',
  OWNER_REQUEST: 'OWNER_REQUEST',
  CODE_UPDATE: 'CODE_UPDATE',
  SITE_CONDITION: 'SITE_CONDITION',
  DESIGN_OPTIMIZE: 'DESIGN_OPTIMIZE',
} as const
export type ChangeCategory = (typeof ChangeCategory)[keyof typeof ChangeCategory]

export const CHANGE_CATEGORY_LABEL: Record<ChangeCategory, string> = {
  SURVEY_DATA: '勘察资料变化',
  OWNER_REQUEST: '业主要求',
  CODE_UPDATE: '规范更新',
  SITE_CONDITION: '施工条件',
  DESIGN_OPTIMIZE: '设计优化',
}

export const ImpactTargetType = {
  PILE: 'PILE',
  CALCULATION: 'CALCULATION',
  DRAWING: 'DRAWING',
  CONSTRUCTED_PART: 'CONSTRUCTED_PART',
  COST: 'COST',
  SCHEDULE: 'SCHEDULE',
} as const
export type ImpactTargetType = (typeof ImpactTargetType)[keyof typeof ImpactTargetType]

export const IMPACT_TARGET_LABEL: Record<ImpactTargetType, string> = {
  PILE: '受影响桩位',
  CALCULATION: '计算书',
  DRAWING: '图纸',
  CONSTRUCTED_PART: '已施工部位',
  COST: '成本',
  SCHEDULE: '进度',
}

export interface ChangeImpact {
  id: string
  change_id: string
  target_type: ImpactTargetType
  target_type_label?: string | null
  target_id?: string | null
  target_name?: string | null
  impact_desc: string
  severity: string
  /** 涉及已施工部位 —— 最高风险，需立即通知施工方与监理 */
  requires_immediate_notice: boolean
  handled: boolean
  handled_by?: string | null
  handled_by_name?: string | null
  handled_at?: string | null
  handle_note?: string | null
}

export interface ChangeInfo {
  id: string
  project_id: string
  stage_code: StageCode
  stage_label?: string | null
  change_no: string
  title: string
  category?: ChangeCategory | null
  category_label?: string | null
  reason: string
  description?: string | null
  state: ChangeState
  state_label?: string | null
  origin_version_id?: string | null
  new_version_id?: string | null
  impact_pile_count: number
  impact_constructed_count: number
  impact_cost_delta?: number | null
  impact_schedule_days?: number | null
  impact_scope?: Record<string, unknown> | null
  initiator?: string | null
  initiator_name?: string | null
  approver?: string | null
  workflow_instance_id?: string | null
  current_node?: string | null
  submitted_at?: string | null
  approved_at?: string | null
  closed_at?: string | null
  created_at?: string | null
  impacts: ChangeImpact[]
  available_actions: string[]
  impact_total: number
  impact_handled: number
  has_constructed_impact: boolean
}

export interface ChangeCreateIn {
  stage_code: StageCode
  title: string
  category: ChangeCategory
  reason: string
  description?: string | null
  origin_version_id?: string | null
  change_no?: string | null
}

export interface AffectedPile {
  id: string
  pile_no: string
  zone?: string | null
  pile_type_name?: string | null
  design_length?: number | null
  design_capacity?: number | null
  status: string
  constructed_at?: string | null
}

// ============================================================
// 问题管理与闭环
// ============================================================

export const IssueStatus = {
  OPEN: 'OPEN',
  IN_PROGRESS: 'IN_PROGRESS',
  PENDING_VERIFY: 'PENDING_VERIFY',
  CLOSED: 'CLOSED',
  ESCALATED: 'ESCALATED',
} as const
export type IssueStatus = (typeof IssueStatus)[keyof typeof IssueStatus]

export const ISSUE_STATUS_LABEL: Record<IssueStatus, string> = {
  OPEN: '待处理',
  IN_PROGRESS: '处理中',
  PENDING_VERIFY: '待验证',
  CLOSED: '已闭环',
  ESCALATED: '已升级',
}

export const ISSUE_STATUS_TAG: Record<
  IssueStatus,
  'success' | 'info' | 'warning' | 'danger' | 'primary'
> = {
  OPEN: 'danger',
  IN_PROGRESS: 'primary',
  PENDING_VERIFY: 'warning',
  CLOSED: 'success',
  ESCALATED: 'danger',
}

/** 八段式处理链路 —— 对应设计 PPT 第 8 页那条链路 */
export const IssueActionType = {
  DESCRIBE: 'DESCRIBE',
  QUERY: 'QUERY',
  ANALYZE: 'ANALYZE',
  SUGGEST: 'SUGGEST',
  EXECUTE: 'EXECUTE',
  VERIFY: 'VERIFY',
  CLOSE: 'CLOSE',
  KNOWLEDGE: 'KNOWLEDGE',
} as const
export type IssueActionType = (typeof IssueActionType)[keyof typeof IssueActionType]

export const ISSUE_ACTION_LABEL: Record<IssueActionType, string> = {
  DESCRIBE: '问题描述',
  QUERY: '查询',
  ANALYZE: '分析识别',
  SUGGEST: '建议',
  EXECUTE: '执行',
  VERIFY: '验证',
  CLOSE: '闭环',
  KNOWLEDGE: '知识沉淀',
}

/** 链路顺序，用于进度展示与"下一步"提示 */
export const ISSUE_ACTION_ORDER: IssueActionType[] = [
  'DESCRIBE',
  'QUERY',
  'ANALYZE',
  'SUGGEST',
  'EXECUTE',
  'VERIFY',
  'CLOSE',
  'KNOWLEDGE',
]

export const ISSUE_SOURCE_LABEL: Record<string, string> = {
  REVIEW: '校审',
  SITE: '现场',
  INSPECTION: '检测',
  SELF: '自检',
  MONITOR: '监测',
  AI: 'AI 提示',
}

export const Severity = {
  HIGH: 'HIGH',
  NORMAL: 'NORMAL',
  LOW: 'LOW',
} as const
export type Severity = (typeof Severity)[keyof typeof Severity]

export const SEVERITY_LABEL: Record<Severity, string> = {
  HIGH: '高',
  NORMAL: '中',
  LOW: '低',
}

export const SEVERITY_TAG: Record<Severity, 'danger' | 'warning' | 'info'> = {
  HIGH: 'danger',
  NORMAL: 'warning',
  LOW: 'info',
}

export interface IssueActionInfo {
  id: string
  action_type: IssueActionType
  action_label?: string | null
  sequence: number
  content: string
  is_ai_generated: boolean
  ai_citation?: string | null
  actor?: string | null
  actor_name?: string | null
  acted_at?: string | null
  attachment_version_id?: string | null
  sort: number
}

export interface IssueInfo {
  id: string
  project_id: string
  stage_code: StageCode
  stage_label?: string | null
  issue_no?: string | null
  title: string
  description: string
  source: string
  source_label?: string | null
  issue_type_id?: string | null
  issue_type_name?: string | null
  severity: Severity
  severity_label?: string | null
  status: IssueStatus
  status_label?: string | null
  related_pile_id?: string | null
  related_version_id?: string | null
  related_change_id?: string | null
  raise_by?: string | null
  raise_by_name?: string | null
  raise_at?: string | null
  assignee?: string | null
  assignee_name?: string | null
  due_date?: string | null
  overdue: boolean
  verified_by?: string | null
  verified_at?: string | null
  verify_conclusion?: string | null
  closed_at?: string | null
  closed_by?: string | null
  is_knowledge: boolean
  knowledge_summary?: string | null
  actions: IssueActionInfo[]
  available_actions: string[]
  completed_steps: number
  total_steps: number
}

export interface IssueCreateIn {
  stage_code: StageCode
  title: string
  description: string
  source?: string
  issue_type_id?: string | null
  severity?: Severity
  related_pile_id?: string | null
  related_version_id?: string | null
  related_change_id?: string | null
  assignee?: string | null
  due_date?: string | null
}

export interface IssueSummary {
  total: number
  open: number
  in_progress: number
  pending_verify: number
  closed: number
  escalated: number
  high: number
  overdue_count: number
  overdue_issues: { issue_no?: string | null; title: string; due_date: string }[]
  unclosed: number
  knowledge_count: number
  by_status: Record<string, number>
  by_source: Record<string, number>
}

/** 知识条目（AI 检索的数据来源） */
export interface KnowledgeItem {
  issue_id: string
  issue_no?: string | null
  title: string
  stage_code?: StageCode | null
  stage_label?: string | null
  severity?: Severity | null
  knowledge_summary?: string | null
  closed_at?: string | null
  project_id?: string | null
  project_name?: string | null
}

// ============================================================
// 设计成果与交付完整性
// ============================================================

export interface Deliverable {
  type_code: string
  type_name: string
  required: boolean
  note?: string | null

  exists: boolean
  document_id?: string | null
  document_title?: string | null
  doc_no?: string | null

  current_version_no?: string | null
  current_version_state?: string | null
  has_unpublished_newer: boolean
  latest_version_no?: string | null
  latest_version_state?: string | null
  version_count: number

  ready: boolean
  blockers: string[]
  extra_documents: { id: string; title: string; doc_no?: string | null }[]
}

/** 交付关卡。六道全过才允许交付。 */
export interface DeliveryGate {
  gate: number
  code: string
  name: string
  passed: boolean
  detail?: string | null
  blockers: string[]
  suggestion?: string | null
}

export interface DeliveryCheck {
  can_deliver: boolean
  stage_code: StageCode
  checked_at?: string | null
  gates: DeliveryGate[]
  failed_gate_count: number
  blocker_count: number
  summary?: string | null
}

export interface ManifestItem {
  type_name: string
  document_id?: string | null
  title?: string | null
  doc_no?: string | null
  version_no?: string | null
  published_at?: string | null
  is_self_checked: boolean
  file_name?: string | null
}

export interface Manifest {
  project_id: string
  stage_code: StageCode
  generated_at?: string | null
  item_count: number
  items: ManifestItem[]
  note?: string | null
}

// ============================================================
// 文档台账与追溯
// ============================================================

/** 操作人 —— 姓名 + 工号。用户要求"谁做的要看得见"。 */
export interface ActorBrief {
  id: string
  name?: string | null
  employee_no?: string | null
}

/** 一次签认记录 */
export interface LedgerTrace {
  node_code: string
  node_name?: string | null
  unit_code?: string | null
  unit_label?: string | null
  action?: string | null
  comment?: string | null
  actor?: ActorBrief | null
  acted_at?: string | null
  round: number
}

/**
 * 台账的一行。
 *
 * 回答三个问题：文件是什么、**谁做的**、**现在在谁手上**。
 * `primary_unit` 是文件丢了要找的那个单位。
 */
export interface LedgerItem {
  document_id: string
  doc_no?: string | null
  title: string
  category_name?: string | null
  stage_code?: StageCode | null
  stage_label?: string | null
  discipline?: string | null
  secret_level?: string | null

  /** 当前该看的状态：在途优先 → 已发布 → 最新 */
  effective_version_no?: string | null
  effective_state?: DocumentState | null
  effective_state_label?: string | null
  current_version_no?: string | null
  current_state?: DocumentState | null
  current_state_label?: string | null
  latest_version_no?: string | null
  latest_state?: DocumentState | null
  version_count: number

  /** 主办单位 —— 该阶段矩阵里的主要责任单位 */
  primary_unit?: UnitCode | null
  primary_unit_label?: string | null

  created_by?: ActorBrief | null
  current_uploaded_by?: ActorBrief | null
  current_uploaded_at?: string | null
  published_by?: ActorBrief | null
  published_at?: string | null

  inflight_version_no?: string | null
  pending_units: string[]
  pending_unit_labels: string[]
  /** 待签任务数（0 且未发布 = 还没提交；>0 = 提交了在等人签） */
  pending_count: number
  /** 文件现在卡在谁那里 */
  waits_on?: string | null
  awaiting_me: boolean
  workflow_finished: boolean

  trace: LedgerTrace[]
}

export interface Ledger {
  project_id: string
  stage_code?: StageCode | null
  generated_at?: string | null
  item_count: number
  awaiting_count: number
  items: LedgerItem[]
}

export interface StageResponsibilityUnit {
  unit_code: UnitCode
  unit_label?: string | null
  responsibility: Responsibility
  responsibility_label?: string | null
}

export interface StageResponsibility {
  stage_code: StageCode
  stage_label?: string | null
  primary_unit?: UnitCode | null
  inaround_count: number
  units_detail: StageResponsibilityUnit[]
}

// ============================================================
// 工作台（跨项目交办事项）
// ============================================================

/** 一条交办事项。kind 区分三类：等我签认 / 被退回 / 我经手在途 */
export interface WorkItem {
  kind: 'AWAITING_ME' | 'RETURNED_TO_ME' | 'INFLIGHT' | string
  task_id?: string | null
  project_id: string
  project_name?: string | null
  project_short_name?: string | null
  stage_code?: StageCode | null
  node_code?: string | null
  node_name?: string | null
  my_unit?: UnitCode | null
  my_unit_label?: string | null

  document_id?: string | null
  doc_no?: string | null
  title?: string | null
  version_no?: string | null
  version_state?: DocumentState | null
  version_state_label?: string | null

  submitted_by?: string | null
  submitted_by_no?: string | null
  submitted_at?: string | null

  due_at?: string | null
  days_left?: number | null
  overdue: boolean
  round?: number | null

  pending_units?: string[]
  pending_unit_labels?: string[]
}

export interface StageWorkBucket {
  stage_code: string
  stage_label?: string | null
  awaiting: WorkItem[]
  returned: WorkItem[]
}

export interface Workbench {
  user_id?: string | null
  project_id?: string | null
  generated_at?: string | null
  awaiting_count: number
  returned_count: number
  inflight_count: number
  overdue_count: number
  awaiting: WorkItem[]
  returned: WorkItem[]
  inflight: WorkItem[]
  by_stage: StageWorkBucket[]
}

// ============================================================
// AI 问答
// ============================================================

export interface AIProviderStatus {
  mode: string
  available: boolean
  model?: string | null
  base_url_configured: boolean
  allow_cross_project: boolean
  log_retention_days: number
  note?: string | null
}

export interface AICitation {
  id?: string | null
  chunk_id?: string | null
  source_type?: string | null
  source_version_id?: string | null
  document_id?: string | null
  document_title?: string | null
  doc_no?: string | null
  version_no?: string | null
  section_path?: string | null
  page_no?: number | null
  /** 人话定位串，如「详勘 V2.0 第4章 P.15」 */
  locator?: string | null
  quoted_text?: string | null
  score?: number | null
}

/** 四段式回答。has_citation=false 时**不应展示**。 */
export interface AIAnswer {
  conversation_id: string
  message_id: string
  question: string
  content: string
  conclusion?: string | null
  basis?: string | null
  uncertainty?: string | null
  disclaimer?: string | null
  is_complete: boolean
  has_citation: boolean
  citations: AICitation[]
  degraded: boolean
  degrade_reason?: string | null
  provider?: string | null
  model?: string | null
  latency_ms?: number | null
}

export interface AIMessage {
  id: string
  role: 'user' | 'assistant' | string
  content: string
  conclusion?: string | null
  uncertainty?: string | null
  disclaimer?: string | null
  has_citation: boolean
  model?: string | null
  provider?: string | null
  latency_ms?: number | null
  error?: string | null
  feedback?: string | null
  feedback_note?: string | null
  created_at?: string | null
  citations: AICitation[]
}

export interface AIConversation {
  id: string
  project_id: string
  stage_code?: StageCode | null
  title?: string | null
  message_count: number
  created_at?: string | null
  updated_at?: string | null
}
