/** 接口方法。每个方法对应后端一个端点，改动需同步 backend/app/api/。 */
import { del, get, getFull, http, patch, post, postFull, put } from './http'
import type {
  AffectedPile,
  AIAnswer,
  AICitation,
  AIConversation,
  AIMessage,
  AIProviderStatus,
  AdminOptions,
  AdminOverview,
  AdminPermissionAssignment,
  AdminUser,
  AdminUserCreateIn,
  AdminUserUpdateIn,
  ChangeCreateIn,
  ChangeInfo,
  ChangePasswordIn,
  CurrentUser,
  Deliverable,
  DeliveryCheck,
  DesignInputSummary,
  DesignParam,
  DictCategory,
  DictItem,
  DocumentCreateIn,
  DocumentInfo,
  DocumentVersionInfo,
  IssueActionType,
  IssueCreateIn,
  IssueInfo,
  IssueSummary,
  KnowledgeItem,
  Ledger,
  LoginRequest,
  Manifest,
  MyTaskInfo,
  PileInfo,
  BoreholeInfo,
  LicenseInfo,
  MonitoringPointInfo,
  CatalogDocument,
  ChecklistItem,
  ProjectCreateIn,
  ProjectInfo,
  ProjectUpdateIn,
  ProjectMemberCandidate,
  ProjectMemberCreateIn,
  ProjectMemberInfo,
  ProfileUpdateIn,
  PileConditions,
  PileGeo,
  PileReportIn,
  PileReportOut,
  PileSelectionOptions,
  PileSelectionRecord,
  PileSelectionSaveIn,
  PileSuggestion,
  StageOption,
  StageResponsibility,
  StaleRefreshResult,
  TokenPair,
  Workbench,
  WorkflowTrace,
} from './types'

// ---------------- 系统管理控制台 ----------------

export const adminApi = {
  overview: () => get<AdminOverview>('/admin/overview'),
  options: () => get<AdminOptions>('/admin/options'),
  users: (keyword?: string) =>
    get<AdminUser[]>('/admin/users', keyword ? { keyword } : undefined),
  createUser: (body: AdminUserCreateIn) => post<AdminUser>('/admin/users', body),
  updateUser: (id: string, body: AdminUserUpdateIn) => patch<AdminUser>(`/admin/users/${id}`, body),
  resetPassword: (id: string, password: string) =>
    post<{ user_id: string; message: string }>(`/admin/users/${id}/reset-password`, { password }),
  assignPermission: (id: string, body: AdminPermissionAssignment) =>
    post<AdminUser>(`/admin/users/${id}/permissions`, body),
  revokePermission: (id: string, memberId: string) =>
    del<AdminUser>(`/admin/users/${id}/permissions/${memberId}`),
}

// ---------------- 认证 ----------------

export const authApi = {
  login: (body: LoginRequest) => post<TokenPair>('/auth/login', body),
  refresh: (refresh_token: string) => post<TokenPair>('/auth/refresh', { refresh_token }),
  /** 当前用户 + 所属单位 + 在每个项目上的角色与权限范围 */
  me: () => get<CurrentUser>('/auth/me'),
  stageOptions: () => get<StageOption[]>('/auth/stage-options'),
  updateMe: (body: ProfileUpdateIn) => patch<CurrentUser>('/auth/me', body),
  changePassword: (body: ChangePasswordIn) =>
    post<{ message: string }>('/auth/change-password', body),
}

// ---------------- 项目 ----------------

export const projectApi = {
  /** 我的项目列表（后端已按权限过滤，无权限的项目不会出现） */
  list: (params?: { status?: string; keyword?: string }) =>
    get<ProjectInfo[]>('/projects', params as Record<string, unknown>),
  detail: (id: string) => get<ProjectInfo>(`/projects/${id}`),
  create: (body: ProjectCreateIn) => post<ProjectInfo>('/projects', body),
  update: (id: string, body: ProjectUpdateIn) => patch<ProjectInfo>(`/projects/${id}`, body),
  members: (id: string) => get<ProjectMemberInfo[]>(`/projects/${id}/members`),
  /** 建设单位管理员审核通过项目（待审核 → 进行中） */
  approve: (id: string) => post<ProjectInfo>(`/projects/${id}/approve`),
  memberCandidates: (id: string) =>
    get<ProjectMemberCandidate[]>(`/projects/${id}/member-candidates`),
  addMember: (id: string, body: ProjectMemberCreateIn) =>
    post<{ message: string; user_id: string; unit_code: string }>(`/projects/${id}/members`, body),
}

// ---------------- 标准文档清单 ----------------
export const catalogApi = {
  documents: (stage?: string) =>
    get<CatalogDocument[]>('/catalog/documents', stage ? { stage } : undefined),
}

// ---------------- 桩基选型（设计阶段） ----------------

export const pileSelectionApi = {
  /** 可选桩型（含典型参数组合）与条件说明 */
  options: (projectId: string) =>
    get<PileSelectionOptions>(`/projects/${projectId}/pile-selection/options`),
  /** 试算：给定条件（+可选勘察参数）跑规则引擎，不落库 */
  suggest: (projectId: string, body: { conditions: PileConditions; geo?: PileGeo | null }) =>
    post<PileSuggestion>(`/projects/${projectId}/pile-selection/suggest`, body),
  /** 读取已保存的选型方案（没有则返回 null） */
  get: (projectId: string) =>
    get<PileSelectionRecord | null>(`/projects/${projectId}/pile-selection`),
  /** 保存/确认选型方案（需设计阶段编辑权） */
  save: (projectId: string, body: PileSelectionSaveIn) =>
    put<PileSelectionRecord>(`/projects/${projectId}/pile-selection`, body),
  /** 生成评估报告（试算，不落库） */
  previewReport: (projectId: string, body: PileReportIn) =>
    post<PileReportOut>(`/projects/${projectId}/pile-selection/report`, body),
  /** 生成并保存评估报告（需设计阶段编辑权） */
  saveReport: (projectId: string, body: PileReportIn) =>
    put<PileReportOut>(`/projects/${projectId}/pile-selection/report`, body),
  /** 已保存报告的下载地址（默认内嵌预览，&download=1 强制另存为） */
  reportUrl: (projectId: string, download = false) =>
    `/api/v1/projects/${projectId}/pile-selection/report.txt${download ? '?download=1' : ''}`,
}

// ---------------- 字典 ----------------

export const dictApi = {
  categories: (withItems = true) =>
    get<DictCategory[]>('/dict/categories', { with_items: withItems }),
  items: (category: string) => get<DictItem[]>('/dict/items', { category }),
}

// ---------------- 文件与版本 ----------------

export const documentApi = {
  list: (
    projectId: string,
    params?: { stage?: string; category_id?: string; keyword?: string; with_versions?: boolean },
  ) => get<DocumentInfo[]>(`/projects/${projectId}/documents`, params as Record<string, unknown>),

  detail: (documentId: string) => get<DocumentInfo>(`/documents/${documentId}`),

  /** 硬删除文档（误传）。后端限制：已发布不可删。 */
  delete: (documentId: string) => del<{ ok: boolean; deleted: string }>(`/documents/${documentId}`),

  create: (body: DocumentCreateIn) => post<DocumentInfo>('/documents', body),

  versions: (documentId: string) =>
    get<DocumentVersionInfo[]>(`/documents/${documentId}/versions`),

  version: (versionId: string) => get<DocumentVersionInfo>(`/versions/${versionId}`),

  /** 上传新版本（multipart，需要文件本体） */
  async uploadVersion(
    documentId: string,
    file: File,
    opts?: { change_summary?: string; version_no?: string; remark?: string },
  ): Promise<DocumentVersionInfo> {
    const fd = new FormData()
    fd.append('file', file)
    if (opts?.change_summary) fd.append('change_summary', opts.change_summary)
    if (opts?.version_no) fd.append('version_no', opts.version_no)
    if (opts?.remark) fd.append('remark', opts.remark)
    const resp = await http.post(`/documents/${documentId}/versions`, fd, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
    return resp.data.data as DocumentVersionInfo
  },

  submit: (versionId: string) => post<DocumentVersionInfo>(`/versions/${versionId}/submit`),

  decide: (versionId: string, action: 'APPROVE' | 'RETURN' | 'REJECT', comment?: string, allowSelfCheck = false) =>
    post<DocumentVersionInfo>(`/versions/${versionId}/decide`, {
      action,
      comment,
      allow_self_check: allowSelfCheck,
    }),

  /** 发布。返回完整包体，因为 message 里会回带"来源参数需重新核验"的提示。 */
  publish: (versionId: string, voidReasonForPrevious?: string) =>
    postFull<DocumentVersionInfo>(`/versions/${versionId}/publish`, {
      void_reason_for_previous: voidReasonForPrevious,
    }),

  startRevision: (documentId: string, reason: string) =>
    post<DocumentVersionInfo>(`/documents/${documentId}/revision`, { reason }),

  void: (versionId: string, reason: string) =>
    post<DocumentVersionInfo>(`/versions/${versionId}/void`, { reason }),

  downloadToken: (versionId: string) =>
    get<{ file_id: string; version_id: string; expires_at: number; ttl_seconds: number; url: string }>(
      `/versions/${versionId}/download-token`,
    ),

  trace: (versionId: string) => get<WorkflowTrace | null>(`/tasks/versions/${versionId}/trace`),
}

// ---------------- 设计输入 ----------------

export const designInputApi = {
  list: (projectId: string, params?: { group?: string; verify_status?: string; only_unverified?: boolean }) =>
    get<DesignParam[]>(`/projects/${projectId}/design-inputs`, params as Record<string, unknown>),

  summary: (projectId: string) =>
    get<DesignInputSummary>(`/projects/${projectId}/design-inputs/summary`),

  detail: (projectId: string, paramId: string) =>
    get<DesignParam>(`/projects/${projectId}/design-inputs/${paramId}`),

  verify: (
    projectId: string,
    paramId: string,
    body: { action: string; new_value_num?: number; new_value_text?: string; note?: string },
  ) => post<DesignParam>(`/projects/${projectId}/design-inputs/${paramId}/verify`, body),

  relinkSource: (projectId: string, paramId: string, newVersionId: string) =>
    post<DesignParam>(`/projects/${projectId}/design-inputs/${paramId}/relink-source`, {
      new_version_id: newVersionId,
    }),

  lock: (projectId: string) =>
    post<{ locked_count: number; locked_at: string }>(`/projects/${projectId}/design-inputs/lock`, {}),

  unlock: (projectId: string, reason: string) =>
    post<{ unlocked_count: number; reason: string }>(
      `/projects/${projectId}/design-inputs/unlock`,
      { reason },
    ),

  refreshStale: (projectId: string) =>
    post<StaleRefreshResult>(`/projects/${projectId}/design-inputs/refresh-stale`),
}

// ---------------- 待办 ----------------

export const taskApi = {
  my: (params?: { project_id?: string; overdue_only?: boolean }) =>
    get<MyTaskInfo[]>('/tasks/my', params as Record<string, unknown>),
  trace: (instanceId: string) => get<WorkflowTrace>(`/tasks/instances/${instanceId}`),
}

// ---------------- 设计变更与影响分析 ----------------

export const changeApi = {
  list: (projectId: string, params?: { state?: string; stage?: string }) =>
    get<ChangeInfo[]>(`/projects/${projectId}/changes`, params as Record<string, unknown>),

  detail: (projectId: string, changeId: string) =>
    get<ChangeInfo>(`/projects/${projectId}/changes/${changeId}`),

  create: (projectId: string, body: ChangeCreateIn) =>
    post<ChangeInfo>(`/projects/${projectId}/changes`, body),

  /** 执行影响分析。返回完整包体，因为 message 会提示"涉及已施工桩位 N 根"。 */
  analyze: (
    projectId: string,
    changeId: string,
    body: { scope_zones?: string[]; affected_pile_ids?: string[] },
  ) => postFull<ChangeInfo>(`/projects/${projectId}/changes/${changeId}/analyze`, body),

  affectedPiles: (projectId: string, changeId: string, onlyConstructed = false) =>
    get<AffectedPile[]>(`/projects/${projectId}/changes/${changeId}/affected-piles`, {
      only_constructed: onlyConstructed,
    }),

  handleImpact: (projectId: string, changeId: string, impactId: string, note: string) =>
    post<ChangeInfo>(
      `/projects/${projectId}/changes/${changeId}/impacts/${impactId}/handle`,
      { note },
    ),

  notify: (projectId: string, changeId: string) =>
    postFull<{ sent: { impact_id: string; target_name: string; notified_to: string[] }[] }>(
      `/projects/${projectId}/changes/${changeId}/notify`,
    ),

  submit: (projectId: string, changeId: string) =>
    post<ChangeInfo>(`/projects/${projectId}/changes/${changeId}/submit`),

  decide: (
    projectId: string,
    changeId: string,
    action: 'APPROVE' | 'RETURN' | 'REJECT',
    comment?: string,
    allowSelfCheck = false,
  ) =>
    post<ChangeInfo>(`/projects/${projectId}/changes/${changeId}/decide`, {
      action,
      comment,
      allow_self_check: allowSelfCheck,
    }),

  close: (projectId: string, changeId: string) =>
    post<ChangeInfo>(`/projects/${projectId}/changes/${changeId}/close`),
}

// ---------------- 问题管理与闭环 ----------------

export const issueApi = {
  list: (
    projectId: string,
    params?: { stage?: string; status?: string; source?: string; severity?: string; only_unclosed?: boolean },
  ) => get<IssueInfo[]>(`/projects/${projectId}/issues`, params as Record<string, unknown>),

  summary: (projectId: string) =>
    get<IssueSummary>(`/projects/${projectId}/issues/summary`),

  detail: (projectId: string, issueId: string) =>
    get<IssueInfo>(`/projects/${projectId}/issues/${issueId}`),

  create: (projectId: string, body: IssueCreateIn) =>
    post<IssueInfo>(`/projects/${projectId}/issues`, body),

  /** 追加一条处理记录。链路不可跳步，后端会校验。 */
  addAction: (
    projectId: string,
    issueId: string,
    body: {
      action_type: IssueActionType
      content: string
      is_ai_generated?: boolean
      ai_citation?: string
    },
  ) => post<IssueInfo>(`/projects/${projectId}/issues/${issueId}/actions`, body),

  reopen: (projectId: string, issueId: string, reason: string) =>
    post<IssueInfo>(`/projects/${projectId}/issues/${issueId}/reopen`, { reason }),

  /** 沉淀为知识条目。只有已闭环问题才能沉淀。 */
  consolidate: (projectId: string, issueId: string, summary?: string) =>
    post<IssueInfo>(`/projects/${projectId}/issues/${issueId}/consolidate`, {
      summary: summary ?? null,
    }),

  projectKnowledge: (projectId: string) =>
    get<KnowledgeItem[]>(`/projects/${projectId}/knowledge`),
}

/** 全局知识库（跨项目检索已沉淀的问题经验） */
export const knowledgeApi = {
  search: (params?: { keyword?: string; stage?: string; limit?: number }) =>
    get<KnowledgeItem[]>('/knowledge', params as Record<string, unknown>),
}

// ---------------- 设计成果与交付 ----------------

export const deliverableApi = {
  list: (projectId: string, stage?: string) =>
    get<Deliverable[]>(`/projects/${projectId}/deliverables`, stage ? { stage } : undefined),

  /** 交付前完整性检查（六道关卡）。返回完整包体以便透传后端汇总说明。 */
  check: (projectId: string, stage?: string) =>
    getFull<DeliveryCheck>(
      `/projects/${projectId}/deliverables/check`,
      stage ? { stage } : undefined,
    ),

  manifest: (projectId: string, stage?: string) =>
    get<Manifest>(`/projects/${projectId}/deliverables/manifest`, stage ? { stage } : undefined),
}

// ---------------- 文档台账与追溯 ----------------

export const ledgerApi = {
  /** 项目文档台账 —— 谁上传、谁签认、现在在谁手上 */
  list: (projectId: string, params?: { stage?: string; awaiting_me?: boolean }) =>
    get<Ledger>(`/projects/${projectId}/ledger`, params as Record<string, unknown>),

  /** 只列"等我签认"的文件 */
  awaitingMe: (projectId: string) => get<Ledger>(`/projects/${projectId}/ledger/awaiting-me`),

  /** 七阶段责任总览 —— 哪个阶段谁主办 */
  stageResponsibility: (projectId: string) =>
    get<StageResponsibility[]>(`/projects/${projectId}/stage-responsibility`),
}

// ---------------- 标准清单（按阶段待上传 / 不需要 / 暂未上传） ----------------

export const checklistApi = {
  list: (projectId: string, stage?: string) =>
    get<ChecklistItem[]>(`/projects/${projectId}/checklist`, stage ? { stage } : undefined),

  setStatus: (projectId: string, docCode: string, body: { status: string; reason?: string | null }) =>
    post<{ doc_code: string; status: string; reason: string | null }>(
      `/projects/${projectId}/checklist/${docCode}/status`,
      body,
    ),

  /** 按清单条目上传文件（含更新版本，multipart） */
  async upload(projectId: string, docCode: string, file: File, versionNo?: string) {
    const fd = new FormData()
    fd.append('file', file)
    if (versionNo) fd.append('version_no', versionNo)
    const resp = await http.post(`/projects/${projectId}/checklist/${docCode}/upload`, fd, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
    return resp.data.data as { doc_code: string; status: string; document_id: string; version_id: string }
  },
}

// ---------------- 桩位 / 试桩台账 ----------------

export const pileApi = {
  list: (projectId: string, isTestPile?: boolean) =>
    get<PileInfo[]>(`/projects/${projectId}/piles`, isTestPile === undefined ? undefined : { is_test_pile: isTestPile }),

  update: (pileId: string, body: { actual_capacity?: number | null; actual_length?: number | null; detection_method?: string | null; review_status?: string | null; review_note?: string | null; status?: string; remark?: string | null }) =>
    patch<PileInfo>(`/piles/${pileId}`, body),
}

// ---------------- 钻孔台账 ----------------

export const boreholeApi = {
  list: (projectId: string) => get<BoreholeInfo[]>(`/projects/${projectId}/boreholes`),

  create: (projectId: string, body: { borehole_no: string; x?: number | null; y?: number | null; depth?: number | null; elevation?: number | null; survey_date?: string | null; remark?: string | null }) =>
    post<BoreholeInfo>(`/projects/${projectId}/boreholes`, body),

  update: (boreholeId: string, body: { x?: number | null; y?: number | null; depth?: number | null; elevation?: number | null; survey_date?: string | null; remark?: string | null }) =>
    patch<BoreholeInfo>(`/boreholes/${boreholeId}`, body),

  delete: (boreholeId: string) => del<{ ok: boolean; deleted: string }>(`/boreholes/${boreholeId}`),
}

// ---------------- 证照台账 ----------------

export const licenseApi = {
  list: (projectId: string) => get<LicenseInfo[]>(`/projects/${projectId}/licenses`),

  create: (projectId: string, body: { name: string; license_no?: string | null; authority?: string | null; issue_date?: string | null; valid_until?: string | null; remark?: string | null }) =>
    post<LicenseInfo>(`/projects/${projectId}/licenses`, body),

  update: (licenseId: string, body: { license_no?: string | null; authority?: string | null; issue_date?: string | null; valid_until?: string | null; remark?: string | null }) =>
    patch<LicenseInfo>(`/licenses/${licenseId}`, body),

  delete: (licenseId: string) => del<{ ok: boolean; deleted: string }>(`/licenses/${licenseId}`),
}

// ---------------- 监测点台账 ----------------

export const monitoringApi = {
  list: (projectId: string) => get<MonitoringPointInfo[]>(`/projects/${projectId}/monitoring-points`),

  create: (projectId: string, body: { point_no: string; monitor_item?: string | null; threshold?: number | null; latest_value?: number | null; unit?: string | null; last_measured_at?: string | null; remark?: string | null }) =>
    post<MonitoringPointInfo>(`/projects/${projectId}/monitoring-points`, body),

  update: (pointId: string, body: { monitor_item?: string | null; threshold?: number | null; latest_value?: number | null; unit?: string | null; last_measured_at?: string | null; remark?: string | null }) =>
    patch<MonitoringPointInfo>(`/monitoring-points/${pointId}`, body),

  delete: (pointId: string) => del<{ ok: boolean; deleted: string }>(`/monitoring-points/${pointId}`),
}

// ---------------- 工作台（跨项目交办事项） ----------------

export const workbenchApi = {
  /** 我的工作（跨项目） */
  myWork: () => get<Workbench>('/workbench/my-work'),

  /** 某项目的交办事项（按阶段聚合） */
  projectWork: (projectId: string) =>
    get<Workbench>(`/workbench/projects/${projectId}/work`),
}

// ---------------- AI 问答 ----------------

export const aiApi = {
  providerStatus: () => get<AIProviderStatus>('/ai/provider-status'),

  ask: (
    projectId: string,
    body: {
      question: string
      conversation_id?: string | null
      stage_code?: string | null
      include_knowledge_base?: boolean
    },
  ) => postFull<AIAnswer>(`/ai/projects/${projectId}/ask`, body),

  conversations: (projectId: string) =>
    get<AIConversation[]>(`/ai/projects/${projectId}/conversations`),

  messages: (conversationId: string) =>
    get<AIMessage[]>(`/ai/conversations/${conversationId}/messages`),

  feedback: (messageId: string, feedback: 'USEFUL' | 'USELESS', note?: string) =>
    post<{ message_id: string; feedback: string }>(`/ai/messages/${messageId}/feedback`, {
      feedback,
      note,
    }),

  /** 仅检索不生成回答。调试检索质量、或直接看原文时用。 */
  retrieve: (projectId: string, q: string, stage?: string, limit = 8) =>
    get<AICitation[]>(`/ai/projects/${projectId}/retrieve`, {
      q,
      ...(stage ? { stage } : {}),
      limit,
    }),

  /** 把已发布版本切片入知识库 */
  indexVersion: (projectId: string, versionId: string) =>
    postFull<{ version_id: string; chunk_count: number }>(
      `/ai/projects/${projectId}/knowledge/index`,
      { version_id: versionId },
    ),
}

export const systemApi = {
  health: () => get<{ status: string; app: string; env: string }>('/health'),
}
