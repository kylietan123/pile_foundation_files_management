<script setup lang="ts">
/**
 * 设计变更与影响分析 —— 设计阶段最有价值的功能界面。
 *
 * 这张页面的核心不是"管理变更单"，而是回答一个问题：
 *   **这个改动会影响什么？**
 *
 * 六类影响自动列出，其中「已施工部位」是最高风险项 ——
 * 桩已经打下去了，桩位再改就是返工或补桩，必须立即通知施工方与监理。
 * 这一项在界面上用红色卡片显著标注，是通用文档系统做不到的。
 */
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'

import { changeApi } from '@/api'
import { explainApiError } from '@/api/http'
import type { AffectedPile, ChangeImpact, ChangeInfo, StageCode } from '@/api/types'
import {
  CHANGE_CATEGORY_LABEL,
  CHANGE_STATE_LABEL,
  CHANGE_STATE_TAG,
  ChangeCategory,
  IMPACT_TARGET_LABEL,
  NODE_LABEL,
  STAGE_LABEL,
  TASK_ACTION_LABEL,
} from '@/api/types'
import { useAuthStore } from '@/stores/auth'
import { formatDate, formatDateTime } from '@/utils/format'

const route = useRoute()
const auth = useAuthStore()
const projectId = computed(() => route.params.id as string)
const stageFilter = computed<StageCode | null>(() => {
  const stage = route.query.stage
  return typeof stage === 'string' && stage ? (stage as StageCode) : null
})
const createStage = computed<StageCode>(() => stageFilter.value || 'DESIGN')

const loading = ref(false)
const error = ref<string | null>(null)
const changes = ref<ChangeInfo[]>([])
const selected = ref<ChangeInfo | null>(null)
const affectedPiles = ref<AffectedPile[]>([])
const pilesLoading = ref(false)

const canEdit = computed(() => {
  const m = auth.membershipOf(projectId.value)
  return !!m && m.actions.includes('EDIT')
})

async function load() {
  loading.value = true
  error.value = null
  try {
    const rows = await changeApi.list(projectId.value)
    changes.value = stageFilter.value
      ? rows.filter((item) => item.stage_code === stageFilter.value)
      : rows
    if (selected.value) {
      const fresh = changes.value.find((c) => c.id === selected.value!.id)
      selected.value = fresh ?? null
    } else if (changes.value.length) {
      selectChange(changes.value[0])
    }
  } catch (e) {
    error.value = explainApiError(e)
  } finally {
    loading.value = false
  }
}

onMounted(load)

async function selectChange(c: ChangeInfo) {
  selected.value = c
  affectedPiles.value = []
  if (c.impact_pile_count > 0) loadPiles(c)
}

async function loadPiles(c: ChangeInfo) {
  pilesLoading.value = true
  try {
    affectedPiles.value = await changeApi.affectedPiles(projectId.value, c.id)
  } catch {
    affectedPiles.value = []
  } finally {
    pilesLoading.value = false
  }
}

async function refreshSelected() {
  if (!selected.value) return
  const fresh = await changeApi.detail(projectId.value, selected.value.id)
  selected.value = fresh
  const idx = changes.value.findIndex((c) => c.id === fresh.id)
  if (idx >= 0) changes.value[idx] = fresh
  if (fresh.impact_pile_count > 0) await loadPiles(fresh)
}

/** ---------------- 新建变更 ---------------- */

const createOpen = ref(false)
const createForm = reactive({
  title: '',
  category: 'SURVEY_DATA' as ChangeCategory,
  reason: '',
})

function openCreate() {
  createForm.title = ''
  createForm.category = 'SURVEY_DATA'
  createForm.reason = ''
  createOpen.value = true
}

async function doCreate() {
  if (!createForm.title.trim() || !createForm.reason.trim()) {
    ElMessage.warning('变更标题与原因都要填写')
    return
  }
  try {
    const c = await changeApi.create(projectId.value, {
      stage_code: createStage.value,
      title: createForm.title,
      category: createForm.category,
      reason: createForm.reason,
    })
    ElMessage.success(`已创建 ${c.change_no}，下一步做影响分析`)
    createOpen.value = false
    await load()
    const fresh = changes.value.find((x) => x.id === c.id)
    if (fresh) selectChange(fresh)
  } catch (e) {
    ElMessage.error(explainApiError(e))
  }
}

/** ---------------- 影响分析 ---------------- */

const analyzeOpen = ref(false)
const analyzeZones = ref<string[]>([])

/** 从已选变更的受影响桩位里提取可选分区 */
const zoneOptions = computed(() => {
  const s = new Set<string>()
  for (const p of affectedPiles.value) if (p.zone) s.add(p.zone)
  return [...s]
})

function openAnalyze() {
  analyzeZones.value = []
  analyzeOpen.value = true
}

async function doAnalyze() {
  if (!selected.value) return
  if (!analyzeZones.value.length) {
    ElMessage.warning('请选择影响范围（分区）。不选范围就只能做文档级分析，无法判断哪些桩位受影响')
    return
  }
  try {
    const r = await changeApi.analyze(projectId.value, selected.value.id, {
      scope_zones: analyzeZones.value,
    })
    analyzeOpen.value = false
    // 后端 message 会提示"涉及已施工桩位 N 根"，必须透传
    if (r.message.includes('已施工')) {
      ElMessage.warning(r.message)
    } else {
      ElMessage.success(r.message)
    }
    await refreshSelected()
  } catch (e) {
    ElMessage.error(explainApiError(e))
  }
}

/** ---------------- 处理影响 ---------------- */

async function doHandle(imp: ChangeImpact) {
  if (!selected.value) return
  const urgent = imp.requires_immediate_notice
  try {
    const { value: note } = await ElMessageBox.prompt(
      urgent
        ? `【高风险】${imp.impact_desc}\n\n` +
          `这是已施工部位。请填写处理说明：确认了什么、通知了哪些单位（施工方/监理）、以什么方式通知的。`
        : `${imp.impact_desc}\n\n请填写处理说明（做了什么）。`,
      `处理：${imp.target_name || IMPACT_TARGET_LABEL[imp.target_type]}`,
      {
        confirmButtonText: '确认已处理',
        cancelButtonText: '取消',
        inputPlaceholder: urgent
          ? '例如：已电话+书面通知施工方与监理，并复核已施工桩位，确认无需返工'
          : '例如：已按变更后参数更新图纸并重新提交校审',
        inputValidator: (v) => (v && v.trim().length >= 6 ? true : '请填写不少于 6 个字的处理说明'),
        type: urgent ? 'warning' : undefined,
      },
    )
    await changeApi.handleImpact(projectId.value, selected.value.id, imp.id, note)
    ElMessage.success('已标记处理')
    await refreshSelected()
  } catch (e) {
    if (e !== 'cancel' && e !== 'close') ElMessage.error(explainApiError(e))
  }
}

/** ---------------- 通知 ---------------- */

async function doNotify() {
  if (!selected.value) return
  try {
    const r = await changeApi.notify(projectId.value, selected.value.id)
    if (r.data.sent.length) {
      ElMessage.success(r.message)
    } else {
      ElMessage.info(r.message)
    }
    await refreshSelected()
  } catch (e) {
    ElMessage.error(explainApiError(e))
  }
}

/** ---------------- 提交 / 审批 / 关闭 ---------------- */

async function doSubmit() {
  if (!selected.value) return
  try {
    await ElMessageBox.confirm(
      `提交 ${selected.value.change_no} 进入审批。\n\n` +
        `注意：影响分析必须先完成 —— 否则审批人无法判断这个变更会影响哪些桩位、` +
        `图纸和已施工部位。`,
      '提交变更审批',
      { confirmButtonText: '确认提交', cancelButtonText: '取消' },
    )
    await changeApi.submit(projectId.value, selected.value.id)
    ElMessage.success('已提交审批')
    await refreshSelected()
  } catch (e) {
    if (e !== 'cancel' && e !== 'close') ElMessage.error(explainApiError(e))
  }
}

async function doDecide(action: 'APPROVE' | 'RETURN') {
  if (!selected.value) return
  const urgent = selected.value.has_constructed_impact
  try {
    const { value: comment } = await ElMessageBox.prompt(
      action === 'APPROVE'
        ? `通过 ${selected.value.change_no}。` +
          (urgent
            ? `\n\n⚠ 本变更涉及已施工桩位 ${selected.value.impact_constructed_count} 根，` +
              `批准即意味着同意返工或补桩，请确认。`
            : '')
        : `退回 ${selected.value.change_no}。退回后影响明细需要重新确认。`,
      action === 'APPROVE' ? '变更审批通过' : '退回变更',
      {
        confirmButtonText: action === 'APPROVE' ? '确认通过' : '确认退回',
        cancelButtonText: '取消',
        inputPlaceholder: '审批意见（建议填写，会保留在审批轨迹里）',
        type: urgent && action === 'APPROVE' ? 'warning' : undefined,
      },
    )
    await changeApi.decide(projectId.value, selected.value.id, action, comment || undefined)
    ElMessage.success(action === 'APPROVE' ? '已通过' : '已退回')
    await refreshSelected()
  } catch (e) {
    if (e !== 'cancel' && e !== 'close') ElMessage.error(explainApiError(e))
  }
}

async function doClose() {
  if (!selected.value) return
  try {
    await ElMessageBox.confirm(
      `关闭 ${selected.value.change_no}。\n\n` +
        `前置条件：全部影响明细都已处理。这是"变更不闭环就不算完成"的强制点 —— ` +
        `否则会出现"变更批了，但图纸没改、施工方没收到通知"的漏洞。`,
      '关闭变更',
      { confirmButtonText: '确认关闭', cancelButtonText: '取消' },
    )
    await changeApi.close(projectId.value, selected.value.id)
    ElMessage.success('变更已关闭')
    await refreshSelected()
  } catch (e) {
    if (e !== 'cancel' && e !== 'close') ElMessage.error(explainApiError(e))
  }
}

/** ---------------- 展示辅助 ---------------- */

const stateTag = (s: string) => CHANGE_STATE_TAG[s as ChangeState] ?? 'info'
type ChangeState = keyof typeof CHANGE_STATE_LABEL

/** 影响明细排序：已施工部位排最前，其余按严重度 */
const sortedImpacts = computed(() => {
  const order: Record<string, number> = {
    CONSTRUCTED_PART: 0,
    PILE: 1,
    CALCULATION: 2,
    DRAWING: 3,
    COST: 4,
    SCHEDULE: 5,
  }
  return [...(selected.value?.impacts ?? [])].sort(
    (a, b) => (order[a.target_type] ?? 9) - (order[b.target_type] ?? 9),
  )
})

function severityTag(s: string): 'danger' | 'warning' | 'info' {
  return s === 'HIGH' ? 'danger' : s === 'NORMAL' ? 'warning' : 'info'
}

function money(v?: number | null): string {
  if (v === null || v === undefined) return '—'
  const sign = v > 0 ? '+' : ''
  return `${sign}${v.toLocaleString('zh-CN', { maximumFractionDigits: 0 })} 元`
}
</script>

<template>
  <div class="page">
    <!-- 顶部 -->
    <div class="head app-card">
      <div>
        <div class="sec-title" style="margin-bottom: 10px">
          设计变更与影响分析
          <span class="more" @click="$router.push({ name: 'project-detail', params: { id: projectId } })">
            返回项目总览
          </span>
        </div>
        <p class="t-grey t-sm" style="margin: 0">
          参数一变，自动列出受影响对象 ——
          <b class="t-red">不依赖人记得去查</b>。
          其中「已施工部位」是最高风险项：桩已打下，桩位再改就是返工或补桩。
        </p>
        <el-tag v-if="stageFilter" size="small" effect="plain" style="margin-top: 10px">
          当前按{{ STAGE_LABEL[stageFilter] }}阶段查看
        </el-tag>
      </div>
      <div class="head-actions">
        <el-button v-if="canEdit" type="primary" @click="openCreate">发起设计变更</el-button>
      </div>
    </div>

    <el-skeleton v-if="loading" :rows="8" animated style="margin-top: 16px" />
    <el-alert v-else-if="error" :title="error" type="error" show-icon :closable="false" />

    <div v-else class="layout">
      <!-- 左：变更列表 -->
      <div class="list app-card">
        <div class="list-h">变更单（{{ changes.length }}）</div>
        <div v-if="!changes.length" class="empty t-grey">暂无变更单</div>
        <div
          v-for="c in changes"
          :key="c.id"
          class="item"
          :class="{ active: selected?.id === c.id, urgent: c.has_constructed_impact }"
          @click="selectChange(c)"
        >
          <div class="it-top">
            <span class="it-no t-mono">{{ c.change_no }}</span>
            <el-tag :type="stateTag(c.state)" size="small" effect="light">
              {{ c.state_label || CHANGE_STATE_LABEL[c.state] }}
            </el-tag>
          </div>
          <div class="it-title">{{ c.title }}</div>
          <div class="it-meta t-grey t-sm">
            <span>{{ c.category_label || CHANGE_CATEGORY_LABEL[c.category as ChangeCategory] }}</span>
            <span v-if="c.impact_total > 0">
              · {{ c.impact_handled }}/{{ c.impact_total }} 项影响已处理
            </span>
          </div>
          <div v-if="c.has_constructed_impact" class="it-urgent">
            涉及已施工桩位 {{ c.impact_constructed_count }} 根
          </div>
        </div>
      </div>

      <!-- 右：详情 -->
      <div class="detail">
        <div v-if="!selected" class="app-card pad t-grey" style="text-align: center; padding: 60px">
          从左侧选择一个变更单
        </div>

        <template v-else>
          <!-- 基本信息 -->
          <div class="app-card pad">
            <div class="d-head">
              <div>
                <div class="d-title">{{ selected.title }}</div>
                <div class="t-grey t-sm">
                  <span class="t-mono">{{ selected.change_no }}</span>
                  · {{ selected.category_label }}
                  · 发起人 {{ selected.initiator_name || '—' }}
                  · {{ formatDate(selected.created_at) }}
                </div>
              </div>
              <div class="d-actions">
                <el-button
                  v-for="a in selected.available_actions"
                  :key="a"
                  size="small"
                  :type="
                    a === 'close' ? 'success' : a === 'approve' || a === 'analyze' ? 'primary' : 'default'
                  "
                  :plain="a === 'notify' || a === 'handle'"
                  @click="
                    a === 'analyze'
                      ? openAnalyze()
                      : a === 'submit'
                        ? doSubmit()
                        : a === 'approve'
                          ? doDecide('APPROVE')
                          : a === 'return'
                            ? doDecide('RETURN')
                            : a === 'notify'
                              ? doNotify()
                              : a === 'close'
                                ? doClose()
                                : null
                  "
                >
                  {{
                    {
                      analyze: '执行影响分析',
                      submit: '提交审批',
                      approve: '审批通过',
                      return: '退回',
                      notify: '通知受影响单位',
                      close: '关闭变更',
                      handle: '处理影响明细',
                    }[a] || a
                  }}
                </el-button>
              </div>
            </div>

            <el-descriptions :column="3" border size="small" style="margin-top: 14px">
              <el-descriptions-item label="状态">
                <el-tag :type="stateTag(selected.state)" size="small" effect="light">
                  {{ selected.state_label }}
                </el-tag>
                <span v-if="selected.current_node" class="t-grey t-sm" style="margin-left: 6px">
                  当前节点 {{ NODE_LABEL[selected.current_node] || selected.current_node }}
                </span>
              </el-descriptions-item>
              <el-descriptions-item label="受影响桩位">
                {{ selected.impact_pile_count }} 根
              </el-descriptions-item>
              <el-descriptions-item label="已施工桩位">
                <span :class="selected.impact_constructed_count > 0 ? 't-red' : 't-grey'">
                  <b>{{ selected.impact_constructed_count }}</b> 根
                </span>
              </el-descriptions-item>
              <el-descriptions-item label="成本影响">
                {{ money(selected.impact_cost_delta) }}
              </el-descriptions-item>
              <el-descriptions-item label="工期影响">
                {{ selected.impact_schedule_days ?? '—' }} 天
              </el-descriptions-item>
              <el-descriptions-item label="影响进度">
                {{ selected.impact_handled }}/{{ selected.impact_total }} 项已处理
              </el-descriptions-item>
            </el-descriptions>

            <div class="reason">
              <div class="rs-title">变更原因</div>
              {{ selected.reason }}
            </div>
          </div>

          <!-- 最高风险提示 -->
          <div v-if="selected.has_constructed_impact" class="urgent-banner">
            <div class="ub-title">⚠ 本变更涉及已施工桩位 {{ selected.impact_constructed_count }} 根</div>
            <div class="ub-body">
              桩已完成施工，桩位或桩长调整将造成<b>返工或补桩</b>。
              必须立即通知<b>施工方与监理</b>，并在处理影响明细时记录通知方式与确认结果。
              这是通用文档管理系统做不到的部分 —— 它管的是文件，管不了"哪根桩已经打下去了"。
            </div>
          </div>

          <!-- 影响明细 -->
          <div class="app-card pad">
            <div class="sec-title">
              影响明细（{{ selected.impact_total }}）
              <span class="more" style="cursor: default">
                {{ selected.impact_handled }}/{{ selected.impact_total }} 已处理
              </span>
            </div>

            <div v-if="!selected.impacts.length" class="t-grey t-sm" style="padding: 12px 0">
              尚未执行影响分析。点击上方「执行影响分析」，
              系统会自动列出受影响桩位、需重算的计算书、需更新的图纸，
              以及已经在施工的部位。
            </div>

            <div
              v-for="imp in sortedImpacts"
              :key="imp.id"
              class="imp"
              :class="{
                'imp-urgent': imp.requires_immediate_notice,
                'imp-done': imp.handled,
              }"
            >
              <div class="imp-l">
                <el-tag
                  :type="imp.requires_immediate_notice ? 'danger' : severityTag(imp.severity)"
                  size="small"
                  effect="light"
                >
                  {{ imp.target_type_label || IMPACT_TARGET_LABEL[imp.target_type] }}
                </el-tag>
                <span class="imp-name">{{ imp.target_name }}</span>
                <el-tag v-if="imp.handled" type="success" size="small" effect="plain">已处理</el-tag>
              </div>
              <div class="imp-desc">{{ imp.impact_desc }}</div>
              <div v-if="imp.handle_note" class="imp-note">
                <b>{{ imp.handled_by_name || '—' }}</b> 于 {{ formatDateTime(imp.handled_at) }} 处理：
                {{ imp.handle_note }}
              </div>
              <div v-if="!imp.handled && canEdit" class="imp-act">
                <el-button size="small" :type="imp.requires_immediate_notice ? 'danger' : 'primary'" plain @click="doHandle(imp)">
                  标记已处理
                </el-button>
              </div>
            </div>
          </div>

          <!-- 受影响桩位 -->
          <div v-if="selected.impact_pile_count > 0" class="app-card pad">
            <div class="sec-title">
              受影响桩位清单（{{ affectedPiles.length }}）
              <span class="more" style="cursor: default">
                <template v-if="selected.impact_scope?.zones">
                  范围：{{ (selected.impact_scope.zones as string[]).join('、') }}
                </template>
              </span>
            </div>
            <el-skeleton v-if="pilesLoading" :rows="3" animated />
            <el-table v-else :data="affectedPiles" size="small" max-height="320" style="width: 100%">
              <el-table-column prop="pile_no" label="桩号" width="120">
                <template #default="{ row }">
                  <span class="t-mono">{{ row.pile_no }}</span>
                </template>
              </el-table-column>
              <el-table-column prop="zone" label="分区" width="100" />
              <el-table-column prop="pile_type_name" label="桩型" min-width="150" />
              <el-table-column label="设计桩长" width="100">
                <template #default="{ row }">{{ row.design_length ?? '—' }} m</template>
              </el-table-column>
              <el-table-column label="承载力" width="110">
                <template #default="{ row }">
                  {{ row.design_capacity ? row.design_capacity.toLocaleString() : '—' }} kN
                </template>
              </el-table-column>
              <el-table-column label="状态" width="130">
                <template #default="{ row }">
                  <el-tag
                    :type="row.status === 'CONSTRUCTED' ? 'danger' : 'info'"
                    size="small"
                    effect="light"
                  >
                    {{ row.status === 'CONSTRUCTED' ? '已施工' : '未施工' }}
                  </el-tag>
                  <div v-if="row.constructed_at" class="t-grey t-sm">
                    {{ formatDate(row.constructed_at) }}
                  </div>
                </template>
              </el-table-column>
            </el-table>
          </div>

          <!-- 规则说明 -->
          <div class="rules">
            <b>变更流程的两道强制关卡（后端拦截，前端只是提示）：</b>
            <ol>
              <li>
                <b>未做影响分析不允许提交审批</b> ——
                否则审批人无法判断这个变更会影响哪些桩位、图纸和已施工部位。
              </li>
              <li>
                <b>影响明细未全部处理不允许关闭变更</b> ——
                防止"变更批了，但图纸没改、施工方没收到通知"的漏洞。
              </li>
            </ol>
          </div>
        </template>
      </div>
    </div>

    <!-- ============ 新建变更 ============ -->
    <el-dialog v-model="createOpen" title="发起设计变更" width="560px">
      <el-form label-width="96px">
        <el-form-item label="变更标题" required>
          <el-input v-model="createForm.title" placeholder="例如：1#楼桩位避让地下管线调整" />
        </el-form-item>
        <el-form-item label="原因分类" required>
          <el-select v-model="createForm.category" style="width: 100%">
            <el-option label="勘察资料变化" value="SURVEY_DATA" />
            <el-option label="业主要求" value="OWNER_REQUEST" />
            <el-option label="规范更新" value="CODE_UPDATE" />
            <el-option label="施工条件" value="SITE_CONDITION" />
            <el-option label="设计优化" value="DESIGN_OPTIMIZE" />
          </el-select>
          <div class="t-grey t-sm" style="margin-top: 4px">
            分类必填 —— 这是后期统计"变更主要来自哪里"的数据基础，能直接支撑质量改进。
          </div>
        </el-form-item>
        <el-form-item label="变更原因" required>
          <el-input
            v-model="createForm.reason"
            type="textarea"
            :rows="4"
            placeholder="说明变更的背景与依据，例如：现场发现市政管线，需将 12 根桩位平移 1.8m 避让"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="createOpen = false">取消</el-button>
        <el-button type="primary" @click="doCreate">创建</el-button>
      </template>
    </el-dialog>

    <!-- ============ 影响分析范围 ============ -->
    <el-dialog v-model="analyzeOpen" title="执行影响分析" width="520px">
      <el-alert
        type="info"
        :closable="false"
        show-icon
        style="margin-bottom: 14px"
        title="请选择变更涉及的施工分区。系统会据此筛出受影响桩位，并识别其中已施工的部分。"
      />
      <el-form label-width="88px">
        <el-form-item label="影响范围" required>
          <el-select
            v-model="analyzeZones"
            multiple
            filterable
            allow-create
            default-first-option
            placeholder="选择或输入分区名，如 1#楼"
            style="width: 100%"
          >
            <el-option v-for="z in zoneOptions" :key="z" :label="z" :value="z" />
          </el-select>
          <div class="t-grey t-sm" style="margin-top: 4px">
            可选多个分区。杭州项目的分区为：1#楼、2#楼（已施工）、商业裙房（未施工）、试桩区。
          </div>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="analyzeOpen = false">取消</el-button>
        <el-button type="primary" @click="doAnalyze">开始分析</el-button>
      </template>
    </el-dialog>
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
  flex: 0 0 auto;
}

.layout {
  display: grid;
  grid-template-columns: 320px 1fr;
  gap: 16px;
  margin-top: 16px;
  align-items: start;
}

/* ---------------- 左侧列表 ---------------- */
.list {
  padding: 0;
  overflow: hidden;
  position: sticky;
  top: 0;
}
.list-h {
  padding: 12px 16px;
  border-bottom: 1px solid var(--line);
  font-weight: 700;
  font-size: 13.5px;
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
.item.urgent.active {
  border-left-color: var(--red);
}
.it-top {
  display: flex;
  align-items: center;
  gap: 8px;
}
.it-no {
  font-size: 12px;
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
.it-urgent {
  margin-top: 5px;
  font-size: 11.5px;
  font-weight: 700;
  color: var(--red);
}

/* ---------------- 右侧详情 ---------------- */
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
  flex: 0 0 auto;
}

.reason {
  margin-top: 14px;
  background: #f7f9fc;
  border-radius: 5px;
  padding: 11px 14px;
  font-size: 12.5px;
  color: var(--ink-2);
  line-height: 1.75;
}
.rs-title {
  font-weight: 700;
  color: var(--grey);
  font-size: 11.5px;
  margin-bottom: 4px;
}

/* ---------------- 高风险横幅 ---------------- */
.urgent-banner {
  background: var(--red-soft);
  border: 1px solid #f0bcbc;
  border-left: 4px solid var(--red);
  border-radius: 6px;
  padding: 14px 18px;
}
.ub-title {
  font-size: 14.5px;
  font-weight: 700;
  color: var(--red);
  margin-bottom: 6px;
}
.ub-body {
  font-size: 12.5px;
  color: #8a2f2f;
  line-height: 1.8;
}

/* ---------------- 影响明细 ---------------- */
.imp {
  border: 1px solid var(--line);
  border-radius: 6px;
  padding: 11px 14px;
  margin-bottom: 10px;
  background: #fff;
}
.imp-urgent {
  border-color: #f0bcbc;
  background: #fffafa;
}
.imp-done {
  background: #f8fbfa;
  border-color: #cfe6e2;
}
.imp-l {
  display: flex;
  align-items: center;
  gap: 8px;
}
.imp-name {
  font-weight: 600;
  font-size: 13px;
  color: var(--ink);
}
.imp-desc {
  margin-top: 6px;
  font-size: 12.5px;
  color: var(--ink-2);
  line-height: 1.7;
}
.imp-note {
  margin-top: 7px;
  font-size: 12px;
  color: #0b6b62;
  background: var(--teal-soft);
  border-radius: 4px;
  padding: 6px 10px;
  line-height: 1.65;
}
.imp-act {
  margin-top: 9px;
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

@media (max-width: 1200px) {
  .layout {
    grid-template-columns: 1fr;
  }
  .list {
    position: static;
  }
}
</style>
