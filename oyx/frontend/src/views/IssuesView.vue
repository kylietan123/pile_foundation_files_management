<script setup lang="ts">
/**
 * 问题管理与闭环。
 *
 * 界面核心是**八段式处理链路**的可见化：
 *   问题描述 → 查询 → 分析识别 → 建议 → 执行 → 验证 → 闭环 → 知识沉淀
 *
 * 这条链的意义在于"可追溯"：
 *   - 链路不可跳步（必须先分析再建议、先执行再验证）
 *   - 闭环必须有验证（"执行了"和"验证有效"是两件事）
 *   - 闭环后才能沉淀为知识，供后续项目与 AI 检索引用
 *
 * 已闭环问题会注明"沉淀"状态 —— 这是产品越用越有价值的地方。
 */
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'

import { issueApi, knowledgeApi } from '@/api'
import { explainApiError } from '@/api/http'
import type { IssueActionInfo, IssueInfo, IssueSummary, KnowledgeItem } from '@/api/types'
import {
  ISSUE_ACTION_LABEL,
  ISSUE_ACTION_ORDER,
  ISSUE_SOURCE_LABEL,
  ISSUE_STATUS_LABEL,
  ISSUE_STATUS_TAG,
  IssueActionType,
  SEVERITY_LABEL,
  SEVERITY_TAG,
  Severity,
} from '@/api/types'
import { useAuthStore } from '@/stores/auth'
import { formatDate, formatDateTime } from '@/utils/format'

const route = useRoute()
const auth = useAuthStore()
const projectId = computed(() => route.params.id as string)

const loading = ref(false)
const error = ref<string | null>(null)
const issues = ref<IssueInfo[]>([])
const summary = ref<IssueSummary | null>(null)
const selected = ref<IssueInfo | null>(null)

/** 只显示未闭环 —— 默认打开，避免长期积累的已闭环问题淹没当前工作 */
const onlyUnclosed = ref(true)

/** 知识库抽屉 */
const knowledgeOpen = ref(false)
const knowledgeItems = ref<KnowledgeItem[]>([])
const knowledgeKeyword = ref('')
const knowledgeLoading = ref(false)

const canEdit = computed(() => !!auth.membershipOf(projectId.value))

async function load() {
  loading.value = true
  error.value = null
  try {
    const [s, list] = await Promise.all([
      issueApi.summary(projectId.value),
      issueApi.list(projectId.value, onlyUnclosed.value ? { only_unclosed: true } : undefined),
    ])
    summary.value = s
    issues.value = list
    if (selected.value) {
      const fresh = list.find((i) => i.id === selected.value!.id)
      selected.value = fresh ?? null
    }
    if (!selected.value && list.length) await selectIssue(list[0])
  } catch (e) {
    error.value = explainApiError(e)
  } finally {
    loading.value = false
  }
}

onMounted(load)

async function selectIssue(i: IssueInfo) {
  try {
    // 列表不返回处理记录，详情才返回
    selected.value = await issueApi.detail(projectId.value, i.id)
  } catch (e) {
    ElMessage.error(explainApiError(e))
  }
}

async function refreshSelected() {
  if (!selected.value) return
  const fresh = await issueApi.detail(projectId.value, selected.value.id)
  selected.value = fresh
  const idx = issues.value.findIndex((x) => x.id === fresh.id)
  if (idx >= 0) issues.value[idx] = fresh
  // 闭环状态变化会影响列表筛选，重新拉一次
  if (fresh.status === 'CLOSED' && onlyUnclosed.value) await load()
  else {
    const s = await issueApi.summary(projectId.value)
    summary.value = s
  }
}

/** ---------------- 新建问题 ---------------- */

const createOpen = ref(false)
const createForm = reactive({
  title: '',
  description: '',
  source: 'REVIEW',
  severity: 'NORMAL' as Severity,
  due_date: '' as string,
})

function openCreate() {
  createForm.title = ''
  createForm.description = ''
  createForm.source = 'REVIEW'
  createForm.severity = 'NORMAL'
  createForm.due_date = ''
  createOpen.value = true
}

async function doCreate() {
  if (!createForm.title.trim() || !createForm.description.trim()) {
    ElMessage.warning('问题标题与描述都要填写')
    return
  }
  try {
    const i = await issueApi.create(projectId.value, {
      stage_code: 'DESIGN',
      title: createForm.title,
      description: createForm.description,
      source: createForm.source,
      severity: createForm.severity,
      due_date: createForm.due_date || null,
    })
    ElMessage.success(`已记录问题 ${i.issue_no}`)
    createOpen.value = false
    await load()
    const fresh = issues.value.find((x) => x.id === i.id)
    if (fresh) await selectIssue(fresh)
  } catch (e) {
    ElMessage.error(explainApiError(e))
  }
}

/** ---------------- 推进处理链路 ---------------- */

/** 各环节的填写提示 —— 让用户知道这一步该写什么 */
const ACTION_HINT: Record<string, { title: string; placeholder: string; tip: string }> = {
  QUERY: {
    title: '查询',
    placeholder: '例如：检索 GB 50007-2011 §5.3、浙江省地方标准，以及本区域同类项目做法',
    tip: '把查了什么、依据哪条规范/哪份文件写清楚，后续复核时能追溯',
  },
  ANALYZE: {
    title: '分析识别',
    placeholder: '例如：经复核，③层取样扰动导致指标偏低，偏差约 14%',
    tip: '写清原因判断，不要只写结论',
  },
  SUGGEST: {
    title: '建议',
    placeholder: '例如：建议①补充原状土复验；②复验前按 280kPa 保守设计。依据：JGJ 94-2008 §5.3.5',
    tip: '建议必须带依据（规范条文或文件页码）',
  },
  EXECUTE: {
    title: '执行',
    placeholder: '例如：已按建议修改桩长并更新布置图，责任人欧雨欣，完成期限 2026-10-20',
    tip: '写清做了什么、谁做的、什么时候完成',
  },
  VERIFY: {
    title: '验证',
    placeholder: '例如：由审核人复核：已核对修改后的图纸与计算书，承载力满足要求，验证通过',
    tip: '必须写清由谁验证、依据什么、结论如何。「已确认」这类空话不算验证',
  },
  CLOSE: {
    title: '闭环',
    placeholder: '例如：验证有效，修改后的设计已发布，问题闭环',
    tip: '闭环是这条路线的终点，之后可沉淀为知识条目',
  },
}

const actionDialog = ref(false)
const actionForm = reactive({
  type: 'QUERY' as string,
  content: '',
})

function openAction(type: string) {
  actionForm.type = type
  actionForm.content = ''
  actionDialog.value = true
}

async function doAction() {
  if (!selected.value) return
  if (!actionForm.content.trim()) {
    ElMessage.warning('请填写内容')
    return
  }
  try {
    await issueApi.addAction(projectId.value, selected.value.id, {
      action_type: actionForm.type as IssueActionType,
      content: actionForm.content,
    })
    ElMessage.success(`已记录「${ISSUE_ACTION_LABEL[actionForm.type as IssueActionType]}」环节`)
    actionDialog.value = false
    await refreshSelected()
  } catch (e) {
    ElMessage.error(explainApiError(e))
  }
}

/** ---------------- 知识沉淀 ---------------- */

async function doConsolidate() {
  if (!selected.value) return
  try {
    await ElMessageBox.confirm(
      `把「${selected.value.title}」沉淀为知识条目。\n\n` +
        `沉淀后该条目会进入跨项目知识库，供后续项目和 AI 检索引用。\n` +
        `请确认摘要里包含了：问题现象、分析结论、处理办法、验证结果 —— ` +
        `否则别人看不懂也复用不了。`,
      '沉淀为知识条目',
      { confirmButtonText: '确认沉淀', cancelButtonText: '先看看摘要', type: 'info' },
    )
  } catch {
    return
  }
  try {
    await issueApi.consolidate(projectId.value, selected.value.id)
    ElMessage.success('已沉淀为知识条目')
    await refreshSelected()
  } catch (e) {
    ElMessage.error(explainApiError(e))
  }
}

/** ---------------- 重新打开 ---------------- */

async function doReopen() {
  if (!selected.value) return
  try {
    const { value: reason } = await ElMessageBox.prompt(
      '重新打开已闭环的问题。\n\n' +
        '这是例外路径：正常应该新建问题而不是续写旧记录（保持记录可追溯）。\n' +
        '只允许在验证发现"处理无效"时使用。',
      '重新打开问题',
      {
        confirmButtonText: '确认重新打开',
        cancelButtonText: '取消',
        inputPlaceholder: '例如：现场反馈抗浮锚杆施工困难，需重新评估方案',
        inputValidator: (v) => (v && v.trim().length >= 6 ? true : '请填写不少于 6 个字的原因'),
        type: 'warning',
      },
    )
    await issueApi.reopen(projectId.value, selected.value.id, reason)
    ElMessage.warning('问题已重新打开')
    await refreshSelected()
  } catch (e) {
    if (e !== 'cancel' && e !== 'close') ElMessage.error(explainApiError(e))
  }
}

/** ---------------- 知识库 ---------------- */

async function openKnowledge() {
  knowledgeOpen.value = true
  knowledgeKeyword.value = ''
  await searchKnowledge()
}

async function searchKnowledge() {
  knowledgeLoading.value = true
  try {
    knowledgeItems.value = await knowledgeApi.search({
      keyword: knowledgeKeyword.value || undefined,
      limit: 100,
    })
  } catch (e) {
    ElMessage.error(explainApiError(e))
    knowledgeItems.value = []
  } finally {
    knowledgeLoading.value = false
  }
}

/** ---------------- 展示辅助 ---------------- */

const statusTag = (s: string) =>
  ISSUE_STATUS_TAG[s as keyof typeof ISSUE_STATUS_TAG] ?? 'info'
const sevTag = (s: string) => SEVERITY_TAG[s as Severity] ?? 'info'

/** 处理链路进度：每一步是否已完成 */
const chainSteps = computed(() => {
  const done = new Set((selected.value?.actions ?? []).map((a) => a.action_type))
  return ISSUE_ACTION_ORDER.map((step, idx) => ({
    step,
    label: ISSUE_ACTION_LABEL[step],
    index: idx + 1,
    done: done.has(step),
    // 是否是"下一步"
    isNext: selected.value?.available_actions.includes(step) ?? false,
  }))
})

function actionOf(step: IssueActionType): IssueActionInfo | undefined {
  return selected.value?.actions.find((a) => a.action_type === step)
}

/** 下一步允许的动作，排除 KNOWLEDGE（单独按钮） */
const nextActions = computed(() =>
  (selected.value?.available_actions ?? []).filter((a) => a !== 'KNOWLEDGE'),
)
</script>

<template>
  <div class="page">
    <!-- 顶部 -->
    <div class="head app-card">
      <div>
        <div class="sec-title" style="margin-bottom: 10px">
          问题管理与闭环
          <span class="more" @click="$router.push({ name: 'project-detail', params: { id: projectId } })">
            返回项目总览
          </span>
        </div>
        <p class="t-grey t-sm" style="margin: 0">
          处理链路：问题描述 → 查询 → 分析识别 → 建议 → 执行 → 验证 → 闭环 → 知识沉淀。
          <b class="t-amber">链路不可跳步，闭环必须先有验证。</b>
        </p>
      </div>
      <div class="head-actions">
        <el-badge v-if="summary?.knowledge_count" :value="summary.knowledge_count" type="success">
          <el-button size="small" @click="openKnowledge">知识库</el-button>
        </el-badge>
        <el-button v-else size="small" @click="openKnowledge">知识库</el-button>
        <el-button v-if="canEdit" type="primary" @click="openCreate">记录问题</el-button>
      </div>
    </div>

    <!-- 统计 -->
    <div v-if="summary" class="stats">
      <div class="stat app-card" :class="{ alert: summary.high > 0 }">
        <div class="lab">未闭环</div>
        <div class="val" :class="summary.unclosed > 0 ? 't-red' : 't-teal'">{{ summary.unclosed }}</div>
        <div class="sub">共 {{ summary.total }} 项</div>
      </div>
      <div class="stat app-card" :class="{ alert: summary.overdue_count > 0 }">
        <div class="lab">逾期</div>
        <div class="val" :class="summary.overdue_count > 0 ? 't-red' : 't-grey'">
          {{ summary.overdue_count }}
        </div>
        <div class="sub">超过计划完成日期</div>
      </div>
      <div class="stat app-card">
        <div class="lab">高危</div>
        <div class="val" :class="summary.high > 0 ? 't-amber' : 't-grey'">{{ summary.high }}</div>
        <div class="sub">严重程度为高</div>
      </div>
      <div class="stat app-card">
        <div class="lab">待验证</div>
        <div class="val" :class="summary.pending_verify > 0 ? 't-blue' : 't-grey'">
          {{ summary.pending_verify }}
        </div>
        <div class="sub">等待确认处理有效</div>
      </div>
      <div class="stat app-card">
        <div class="lab">已沉淀知识</div>
        <div class="val t-teal">{{ summary.knowledge_count }}</div>
        <div class="sub">可供后续项目复用</div>
      </div>
    </div>

    <el-skeleton v-if="loading" :rows="8" animated style="margin-top: 16px" />
    <el-alert v-else-if="error" :title="error" type="error" show-icon :closable="false" />

    <div v-else class="layout">
      <!-- 左：问题列表 -->
      <div class="list app-card">
        <div class="list-h">
          问题（{{ issues.length }}）
          <el-switch
            v-model="onlyUnclosed"
            size="small"
            active-text="只看未闭环"
            style="float: right; --el-switch-font-size: 11px"
            @change="load"
          />
        </div>
        <div v-if="!issues.length" class="empty t-grey">
          {{ onlyUnclosed ? '没有未闭环的问题，很干净' : '暂无问题记录' }}
        </div>
        <div
          v-for="i in issues"
          :key="i.id"
          class="item"
          :class="{
            active: selected?.id === i.id,
            urgent: i.severity === 'HIGH' && i.status !== 'CLOSED',
          }"
          @click="selectIssue(i)"
        >
          <div class="it-top">
            <span class="it-no t-mono">{{ i.issue_no }}</span>
            <el-tag :type="statusTag(i.status)" size="small" effect="light">
              {{ i.status_label || ISSUE_STATUS_LABEL[i.status] }}
            </el-tag>
            <el-tag v-if="i.severity === 'HIGH'" type="danger" size="small" effect="plain">高危</el-tag>
          </div>
          <div class="it-title">{{ i.title }}</div>
          <div class="it-meta t-grey t-sm">
            {{ i.source_label || ISSUE_SOURCE_LABEL[i.source] }}
            · {{ i.completed_steps }}/{{ i.total_steps }} 环节
            <template v-if="i.overdue"> · <span class="t-red">已逾期</span></template>
            <template v-if="i.is_knowledge"> · <span class="t-teal">已沉淀</span></template>
          </div>
        </div>
      </div>

      <!-- 右：详情 -->
      <div class="detail">
        <div v-if="!selected" class="app-card pad t-grey" style="text-align: center; padding: 60px">
          从左侧选择一个问题
        </div>

        <template v-else>
          <!-- 基本信息 -->
          <div class="app-card pad">
            <div class="d-head">
              <div>
                <div class="d-title">{{ selected.title }}</div>
                <div class="t-grey t-sm">
                  <span class="t-mono">{{ selected.issue_no }}</span>
                  · {{ selected.source_label }}
                  · 提出人 {{ selected.raise_by_name || '—' }}
                  · {{ formatDate(selected.raise_at) }}
                  <template v-if="selected.due_date">
                    · 期限 {{ formatDate(selected.due_date) }}
                    <span v-if="selected.overdue" class="t-red">（已逾期）</span>
                  </template>
                </div>
              </div>
              <div class="d-actions">
                <el-tag :type="statusTag(selected.status)" effect="dark" size="large">
                  {{ selected.status_label }}
                </el-tag>
                <el-button
                  v-for="a in nextActions"
                  :key="a"
                  size="small"
                  type="primary"
                  @click="openAction(a)"
                >
                  {{ ISSUE_ACTION_LABEL[a as IssueActionType] }}
                </el-button>
                <el-button
                  v-if="selected.available_actions.includes('KNOWLEDGE')"
                  size="small"
                  type="success"
                  @click="doConsolidate"
                >
                  沉淀为知识
                </el-button>
                <el-button v-if="selected.status === 'CLOSED' && canEdit" size="small" @click="doReopen">
                  重新打开
                </el-button>
              </div>
            </div>

            <el-descriptions :column="3" border size="small" style="margin-top: 14px">
              <el-descriptions-item label="严重程度">
                <el-tag :type="sevTag(selected.severity)" size="small" effect="light">
                  {{ selected.severity_label || SEVERITY_LABEL[selected.severity] }}
                </el-tag>
              </el-descriptions-item>
              <el-descriptions-item label="处理进度">
                {{ selected.completed_steps }} / {{ selected.total_steps }} 环节
              </el-descriptions-item>
              <el-descriptions-item label="负责人">
                {{ selected.assignee_name || '—' }}
              </el-descriptions-item>
            </el-descriptions>

            <!-- 链路进度条：八段式一眼看全 -->
            <div class="chain">
              <div
                v-for="s in chainSteps"
                :key="s.step"
                class="ch"
                :class="{ done: s.done, next: s.isNext && !s.done }"
              >
                <div class="ch-dot">{{ s.done ? '✓' : s.index }}</div>
                <div class="ch-label">{{ s.label }}</div>
              </div>
            </div>

            <el-alert
              v-if="selected.status === 'CLOSED' && !selected.is_knowledge"
              type="success"
              show-icon
              :closable="false"
              style="margin-top: 14px"
              title="问题已闭环，建议沉淀为知识条目"
            >
              <div style="font-size: 12.5px; line-height: 1.7; margin-bottom: 8px">
                沉淀后进入<b>跨项目知识库</b>，供后续项目和 AI 检索引用。
                这是产品越用越有价值的地方 —— 一个项目踩过的坑，别的项目不用再踩。
              </div>
              <el-button size="small" type="success" @click="doConsolidate">立即沉淀</el-button>
            </el-alert>

            <el-alert
              v-if="selected.is_knowledge"
              type="success"
              show-icon
              :closable="false"
              style="margin-top: 14px"
              title="已沉淀为知识条目，可供后续项目检索"
            />
          </div>

          <!-- 问题描述 -->
          <div class="app-card pad">
            <div class="sec-title">问题描述</div>
            <div class="desc">{{ selected.description }}</div>
          </div>

          <!-- 处理链路 -->
          <div class="app-card pad">
            <div class="sec-title">
              处理链路
              <span class="more" style="cursor: default">
                {{ selected.completed_steps }}/{{ selected.total_steps }} 环节
              </span>
            </div>

            <el-timeline style="padding-left: 4px">
              <el-timeline-item
                v-for="step in ISSUE_ACTION_ORDER"
                :key="step"
                :type="actionOf(step) ? (step === 'VERIFY' ? 'success' : 'primary') : 'info'"
                :hollow="!actionOf(step)"
                size="normal"
              >
                <div class="tk">
                  <div class="tk-head">
                    <b>{{ ISSUE_ACTION_LABEL[step] }}</b>
                    <el-tag v-if="actionOf(step)?.is_ai_generated" size="small" type="warning" effect="plain">
                      AI 生成
                    </el-tag>
                    <span v-if="actionOf(step)" class="t-grey t-sm">
                      {{ actionOf(step)!.actor_name || '—' }}
                      · {{ formatDateTime(actionOf(step)!.acted_at) }}
                    </span>
                    <span v-else class="t-grey t-sm">未记录</span>
                  </div>

                  <!-- 同一步骤可能有多次记录（如问题描述的补充） -->
                  <div
                    v-for="a in selected.actions.filter((x) => x.action_type === step)"
                    :key="a.id"
                    class="tk-content"
                  >
                    {{ a.content }}
                    <div v-if="a.ai_citation" class="cite">引用：{{ a.ai_citation }}</div>
                  </div>

                  <div v-if="!actionOf(step) && selected.available_actions.includes(step)" class="tk-next">
                    <el-button size="small" type="primary" plain @click="openAction(step)">
                      记录「{{ ISSUE_ACTION_LABEL[step] }}」
                    </el-button>
                  </div>
                </div>
              </el-timeline-item>
            </el-timeline>
          </div>

          <!-- 知识摘要 -->
          <div v-if="selected.knowledge_summary" class="app-card pad">
            <div class="sec-title">知识摘要<span class="more" style="cursor: default">供后续项目与 AI 检索</span></div>
            <pre class="kn">{{ selected.knowledge_summary }}</pre>
          </div>

          <!-- 规则说明 -->
          <div class="rules">
            <b>问题管理的两道强制关卡（后端拦截，前端只是提示）：</b>
            <ol>
              <li>
                <b>链路不可跳步</b> —— 必须先「分析识别」再「建议」，先「执行」再「验证」。
                跳步会让问题记录失去可追溯性，而这正是设计院最在意的。
              </li>
              <li>
                <b>闭环必须先有验证</b> ——「执行了」和「验证有效」是两件事。
                混在一起会让闭环变成走形式。验证还必须写清由谁验证、依据什么、结论如何。
              </li>
            </ol>
            <div style="margin-top: 8px">
              另外：<b>只有已闭环的问题才能沉淀为知识</b> ——
              未经验证的处理办法不该进入知识库，否则会把错误经验传播到后续项目。
            </div>
          </div>
        </template>
      </div>
    </div>

    <!-- ============ 记录问题 ============ -->
    <el-dialog v-model="createOpen" title="记录问题" width="580px">
      <el-form label-width="88px">
        <el-form-item label="问题标题" required>
          <el-input v-model="createForm.title" placeholder="例如：承台底面标高与地下水位关系需复核" />
        </el-form-item>
        <el-form-item label="问题描述" required>
          <el-input
            v-model="createForm.description"
            type="textarea"
            :rows="4"
            placeholder="写清现象、位置、涉及的数据。描述会自动作为处理链路的第一步"
          />
        </el-form-item>
        <el-form-item label="来源">
          <el-select v-model="createForm.source" style="width: 100%">
            <el-option label="校审" value="REVIEW" />
            <el-option label="现场" value="SITE" />
            <el-option label="检测" value="INSPECTION" />
            <el-option label="自检" value="SELF" />
            <el-option label="监测" value="MONITOR" />
          </el-select>
        </el-form-item>
        <el-form-item label="严重程度">
          <el-select v-model="createForm.severity" style="width: 100%">
            <el-option label="高" value="HIGH" />
            <el-option label="中" value="NORMAL" />
            <el-option label="低" value="LOW" />
          </el-select>
        </el-form-item>
        <el-form-item label="计划完成">
          <el-date-picker
            v-model="createForm.due_date"
            type="date"
            value-format="YYYY-MM-DD"
            placeholder="留空表示不设期限"
            style="width: 100%"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="createOpen = false">取消</el-button>
        <el-button type="primary" @click="doCreate">记录</el-button>
      </template>
    </el-dialog>

    <!-- ============ 推进链路 ============ -->
    <el-dialog
      v-model="actionDialog"
      :title="`记录「${ACTION_HINT[actionForm.type]?.title || actionForm.type}」`"
      width="560px"
    >
      <el-alert
        v-if="ACTION_HINT[actionForm.type]"
        type="info"
        :closable="false"
        show-icon
        style="margin-bottom: 14px"
        :title="ACTION_HINT[actionForm.type].tip"
      />
      <el-input
        v-model="actionForm.content"
        type="textarea"
        :rows="6"
        :placeholder="ACTION_HINT[actionForm.type]?.placeholder || '请填写内容'"
      />
      <template #footer>
        <el-button @click="actionDialog = false">取消</el-button>
        <el-button type="primary" @click="doAction">提交</el-button>
      </template>
    </el-dialog>

    <!-- ============ 知识库 ============ -->
    <el-drawer v-model="knowledgeOpen" title="跨项目知识库" size="720px">
      <div class="kb-search">
        <el-input
          v-model="knowledgeKeyword"
          placeholder="搜索问题、分析结论、处理办法…"
          clearable
          @keyup.enter="searchKnowledge"
        >
          <template #append>
            <el-button @click="searchKnowledge">搜索</el-button>
          </template>
        </el-input>
      </div>

      <el-alert
        type="info"
        :closable="false"
        show-icon
        style="margin-bottom: 14px"
        title="这里汇总所有项目已闭环并沉淀的问题经验"
      >
        <div style="font-size: 12.5px; line-height: 1.7">
          一个项目踩过的坑，别的项目不用再踩。
          <b>这也是 AI 检索层的数据来源</b> ——
          接入向量库后，这里会换成语义检索，接口形态不变。
        </div>
      </el-alert>

      <el-skeleton v-if="knowledgeLoading" :rows="5" animated />
      <div v-else-if="!knowledgeItems.length" class="t-grey" style="padding: 30px; text-align: center">
        没有匹配的知识条目
      </div>
      <div v-else>
        <div v-for="k in knowledgeItems" :key="k.issue_id" class="kb-item">
          <div class="kb-head">
            <span class="kb-title">{{ k.title }}</span>
            <el-tag v-if="k.severity" :type="sevTag(k.severity)" size="small" effect="light">
              {{ SEVERITY_LABEL[k.severity] }}
            </el-tag>
          </div>
          <div class="t-grey t-sm kb-meta">
            <template v-if="k.project_name">{{ k.project_name }} · </template>
            {{ k.stage_label || '—' }}
            <template v-if="k.closed_at"> · 闭环于 {{ formatDate(k.closed_at) }}</template>
          </div>
          <pre class="kb-sum">{{ k.knowledge_summary }}</pre>
        </div>
      </div>
    </el-drawer>
  </div>
</template>

<style scoped>
.page {
  max-width: 1680px;
}

.head {
  display: flex;
  align-items: flex-start;
  gap: 16px;
  padding: 16px 20px;
}
.head-actions {
  margin-left: auto;
  display: flex;
  align-items: center;
  gap: 12px;
  flex: 0 0 auto;
}

/* ---------------- 统计 ---------------- */
.stats {
  display: grid;
  grid-template-columns: repeat(5, 1fr);
  gap: 14px;
  margin-top: 14px;
}
.stat {
  padding: 13px 16px;
}
.stat.alert {
  border-color: var(--amber);
  background: #fffdf7;
}
.stat .lab {
  font-size: 12.5px;
  color: var(--grey);
}
.stat .val {
  font-size: 23px;
  font-weight: 700;
  margin-top: 3px;
  letter-spacing: -0.5px;
}
.stat .sub {
  font-size: 12px;
  color: var(--grey);
  margin-top: 2px;
}

/* ---------------- 两栏 ---------------- */
.layout {
  display: grid;
  grid-template-columns: 340px 1fr;
  gap: 16px;
  margin-top: 16px;
  align-items: start;
}

.list {
  padding: 0;
  overflow: hidden;
  position: sticky;
  top: 0;
}
.list-h {
  padding: 11px 16px;
  border-bottom: 1px solid var(--line);
  font-weight: 700;
  font-size: 13.5px;
  display: flex;
  align-items: center;
}
.empty {
  padding: 30px 16px;
  text-align: center;
  font-size: 13px;
}
.item {
  padding: 11px 16px;
  border-bottom: 1px solid #f0f3f8;
  cursor: pointer;
  transition: background 0.15s;
  border-left: 3px solid transparent;
}
.item:hover {
  background: #f7f9fc;
}
.item.active {
  background: var(--blue-soft);
  border-left-color: var(--blue);
}
.item.urgent {
  border-left-color: var(--red);
}
.it-top {
  display: flex;
  align-items: center;
  gap: 7px;
  flex-wrap: wrap;
}
.it-no {
  font-size: 11.5px;
  color: var(--grey);
}
.it-title {
  font-size: 13.5px;
  font-weight: 600;
  color: var(--ink);
  margin: 5px 0 3px;
  line-height: 1.45;
}
.it-meta {
  font-size: 11.5px;
}

/* ---------------- 详情 ---------------- */
.detail {
  display: flex;
  flex-direction: column;
  gap: 16px;
  min-width: 0;
}
.pad {
  padding: 16px 20px;
}
.d-head {
  display: flex;
  align-items: flex-start;
  gap: 16px;
}
.d-title {
  font-size: 16px;
  font-weight: 700;
  margin-bottom: 4px;
}
.d-actions {
  margin-left: auto;
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  justify-content: flex-end;
  align-items: center;
  flex: 0 0 auto;
}

/* ---------------- 链路进度条 ---------------- */
.chain {
  display: flex;
  gap: 0;
  margin-top: 16px;
  padding: 12px 0;
  border-top: 1px dashed var(--line);
  border-bottom: 1px dashed var(--line);
}
.ch {
  flex: 1;
  text-align: center;
  font-size: 11px;
  color: #b3bdc9;
}
.ch-dot {
  width: 22px;
  height: 22px;
  border-radius: 50%;
  background: #eef1f5;
  color: #b3bdc9;
  display: flex;
  align-items: center;
  justify-content: center;
  margin: 0 auto 5px;
  font-size: 11px;
  font-weight: 700;
}
.ch.done {
  color: var(--teal);
}
.ch.done .ch-dot {
  background: var(--teal);
  color: #fff;
}
.ch.next {
  color: var(--blue);
  font-weight: 700;
}
.ch.next .ch-dot {
  background: var(--blue-soft);
  color: var(--blue);
  box-shadow: 0 0 0 3px rgba(30, 111, 217, 0.16);
}
.ch-label {
  line-height: 1.3;
}

.desc {
  font-size: 13px;
  color: var(--ink-2);
  line-height: 1.85;
  background: #f7f9fc;
  border-radius: 5px;
  padding: 12px 15px;
}

/* ---------------- 处理链路时间线 ---------------- */
.tk-head {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.tk-content {
  margin: 5px 0;
  font-size: 12.5px;
  color: var(--ink-2);
  line-height: 1.75;
  background: #f7f9fc;
  border-radius: 4px;
  padding: 8px 11px;
}
.cite {
  margin-top: 5px;
  padding-top: 5px;
  border-top: 1px dashed var(--line);
  font-size: 11.5px;
  color: var(--blue);
}
.tk-next {
  margin-top: 6px;
}

/* ---------------- 知识摘要 ---------------- */
.kn {
  font-family: 'Microsoft YaHei', monospace;
  font-size: 12.5px;
  line-height: 1.9;
  color: var(--ink-2);
  background: var(--teal-soft);
  border-radius: 5px;
  padding: 13px 16px;
  margin: 0;
  white-space: pre-wrap;
  word-break: break-word;
}

/* ---------------- 规则说明 ---------------- */
.rules {
  background: #f4f8fd;
  border: 1px solid #cfe0f5;
  border-radius: 6px;
  padding: 13px 18px;
  font-size: 12.5px;
  color: #23507f;
  line-height: 1.8;
}
.rules ol {
  margin: 7px 0 0;
  padding-left: 20px;
}
.rules li {
  margin-bottom: 3px;
}

/* ---------------- 知识库抽屉 ---------------- */
.kb-search {
  margin-bottom: 14px;
}
.kb-item {
  border: 1px solid var(--line);
  border-radius: 6px;
  padding: 12px 15px;
  margin-bottom: 10px;
}
.kb-head {
  display: flex;
  align-items: center;
  gap: 8px;
}
.kb-title {
  font-size: 13.5px;
  font-weight: 700;
  color: var(--ink);
}
.kb-meta {
  margin: 4px 0 8px;
}
.kb-sum {
  font-family: inherit;
  font-size: 12.5px;
  line-height: 1.85;
  color: var(--ink-2);
  background: #f7f9fc;
  border-radius: 4px;
  padding: 10px 12px;
  margin: 0;
  white-space: pre-wrap;
  word-break: break-word;
}

@media (max-width: 1300px) {
  .layout {
    grid-template-columns: 1fr;
  }
  .list {
    position: static;
  }
  .stats {
    grid-template-columns: repeat(3, 1fr);
  }
}
</style>
