<script setup lang="ts">
/**
 * 文件台账与追溯。
 *
 * **这是回答"文件丢了谁负责"的那一屏。**
 *
 * 三层信息，逐层回答一个问题：
 *   1. 有哪些文件、什么状态、生效没有     → 版本列 + 状态
 *   2. 谁上传的、谁签认的                 → 负责人列 + 签认轨迹
 *   3. **文件现在在谁手上**（卡在哪个单位）→ 待签单位列
 *
 * 每份文件都标注**主办单位** —— 该阶段《管理流程》矩阵里的主要责任单位。
 * 也就是说：这份文件出问题，找它。
 */
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'

import { ledgerApi } from '@/api'
import { explainApiError } from '@/api/http'
import type { Ledger, LedgerItem, StageResponsibility } from '@/api/types'
import {
  DOCUMENT_STATE_LABEL,
  DocumentState,
  RESPONSIBILITY_LABEL,
  RESPONSIBILITY_TAG,
  STAGE_LABEL,
  STAGE_ORDER,
  UNIT_LABEL,
  UnitCode,
} from '@/api/types'
import { formatDateTime } from '@/utils/format'

const route = useRoute()
const router = useRouter()
const projectId = computed(() => route.params.id as string)

const loading = ref(false)
const error = ref<string | null>(null)
const ledger = ref<Ledger | null>(null)
const board = ref<StageResponsibility[]>([])

/** 筛选 */
const stageFilter = ref<string | null>(null)
const onlyMine = ref(false)

/** 详情抽屉 */
const detailOpen = ref(false)
const active = ref<LedgerItem | null>(null)

async function load() {
  loading.value = true
  error.value = null
  try {
    const [led, bd] = await Promise.all([
      ledgerApi.list(projectId.value, {
        ...(stageFilter.value ? { stage: stageFilter.value } : {}),
        ...(onlyMine.value ? { awaiting_me: true } : {}),
      }),
      ledgerApi.stageResponsibility(projectId.value),
    ])
    ledger.value = led
    board.value = bd
  } catch (e) {
    error.value = explainApiError(e)
  } finally {
    loading.value = false
  }
}

onMounted(load)

function openDetail(item: LedgerItem) {
  active.value = item
  detailOpen.value = true
}

/** ---------------- 展示辅助 ---------------- */

const stateTag = (s?: string | null) => {
  if (!s) return 'info'
  if (s === 'PUBLISHED') return 'success'
  if (s === 'APPROVED') return 'primary'
  if (s === 'VOID') return 'info'
  if (s === 'DRAFT' || s === 'REVISING') return 'info'
  return 'warning'
}

const stateLabel = (s?: string | null) =>
  s ? DOCUMENT_STATE_LABEL[s as DocumentState] || s : '—'

/** 文件"现在在谁手上"的一句话。
 *
 * 关键是区分三种情况，不能混：
 *   有待签任务      → 提交了，在等某单位签认
 *   流程已签完      → 签认完成，待发布
 *   已发布          → 无人待办
 *   都没有          → **还没提交**（此前把这种情况说成"等待某单位签认"是错的，
 *                     那时其实文件还在自己手上，没人需要签）
 */
function locationText(i: LedgerItem): string {
  if (i.pending_count > 0) return `已提交，等待 ${i.pending_unit_labels.join('、')} 签认`
  if (i.effective_state === 'PUBLISHED') return '已发布，当前有效版本'
  if (i.workflow_finished) return '签认已完成，待发布'
  if (i.effective_state === 'DRAFT' || i.effective_state === 'REVISING') {
    return '尚未提交，文件还在上传单位手上'
  }
  return '未提交'
}

/** 有没有文件卡在签认环节（真正在等别人，不是自己还没交） */
const stuckCount = computed(
  () => ledger.value?.items.filter((i) => i.pending_count > 0).length ?? 0,
)
const awaitingCount = computed(() => ledger.value?.items.filter((i) => i.awaiting_me).length ?? 0)
</script>

<template>
  <div class="page">
    <!-- 顶部 -->
    <div class="head app-card">
      <div class="head-l">
        <div class="sec-title" style="margin-bottom: 10px">
          文件台账与追溯
          <span
            class="more"
            @click="router.push({ name: 'project-detail', params: { id: projectId } })"
          >
            返回项目总览
          </span>
        </div>
        <p class="t-grey t-sm" style="margin: 0">
          每份文件都写明<b class="t-red">主办单位</b>（该阶段的主要责任单位）与
          <b>当前待签单位</b> ——
          <b class="t-amber">文件在哪里、谁负责，一眼看得出来。</b>
          每一次上传与签认都记操作人姓名与工号。
        </p>
      </div>
      <div class="head-actions">
        <el-select
          v-model="stageFilter"
          size="small"
          placeholder="全部阶段"
          clearable
          style="width: 140px"
          @change="load"
        >
          <el-option v-for="s in STAGE_ORDER" :key="s" :label="STAGE_LABEL[s]" :value="s" />
        </el-select>
        <el-checkbox v-model="onlyMine" size="small" @change="load">只看等我处理</el-checkbox>
        <el-button size="small" @click="load">刷新</el-button>
      </div>
    </div>

    <!-- 概览 -->
    <div class="stats">
      <div class="stat app-card">
        <div class="lab">文件总数</div>
        <div class="val">{{ ledger?.item_count ?? 0 }}</div>
        <div class="sub">当前筛选范围内</div>
      </div>
      <div class="stat app-card" :class="{ alert: stuckCount > 0 }">
        <div class="lab">在途签认</div>
        <div class="val" :class="stuckCount > 0 ? 't-amber' : 't-grey'">{{ stuckCount }}</div>
        <div class="sub">卡在签认环节的文件</div>
      </div>
      <div class="stat app-card" :class="{ alert: awaitingCount > 0 }">
        <div class="lab">等我处理</div>
        <div class="val" :class="awaitingCount > 0 ? 't-blue' : 't-grey'">
          {{ awaitingCount }}
        </div>
        <div class="sub">需要我签认</div>
      </div>
      <div class="stat app-card">
        <div class="lab">阶段责任</div>
        <div class="val t-sm" style="font-weight: 600; line-height: 1.5; margin-top: 6px">
          七阶段均已明确主办单位
        </div>
        <div class="sub">由《管理流程》矩阵决定</div>
      </div>
    </div>

    <el-skeleton v-if="loading" :rows="8" animated style="margin-top: 16px" />
    <el-alert v-else-if="error" :title="error" type="error" show-icon :closable="false" />

    <template v-else>
      <!-- 台账表 -->
      <div class="app-card pad">
        <div class="sec-title">
          文件台账
          <span class="more" style="cursor: default">
            {{ ledger?.items.length ?? 0 }} 份
            <template v-if="ledger?.generated_at">
              · 生成于 {{ formatDateTime(ledger.generated_at) }}
            </template>
          </span>
        </div>

        <el-table
          v-if="ledger?.items.length"
          :data="ledger.items"
          size="small"
          style="width: 100%"
          @row-click="openDetail"
        >
          <el-table-column label="文件" min-width="230">
            <template #default="{ row }">
              <div class="f-title">{{ row.title }}</div>
              <div class="t-grey t-sm t-mono">
                {{ row.doc_no || '无编号' }}
                <template v-if="row.category_name"> · {{ row.category_name }}</template>
              </div>
            </template>
          </el-table-column>

          <el-table-column label="阶段" width="100">
            <template #default="{ row }">
              <el-tag size="small" effect="plain">
                {{ row.stage_label || STAGE_LABEL[row.stage_code as never] || '—' }}
              </el-tag>
            </template>
          </el-table-column>

          <el-table-column label="主办单位" width="130">
            <template #default="{ row }">
              <el-tag size="small" type="danger" effect="light">
                {{ row.primary_unit_label || '—' }}
              </el-tag>
              <div class="t-grey t-sm">出问题找它</div>
            </template>
          </el-table-column>

          <el-table-column label="版本 / 状态" width="140">
            <template #default="{ row }">
              <b class="t-mono">{{ row.effective_version_no || '—' }}</b>
              <el-tag
                :type="stateTag(row.effective_state)"
                size="small"
                effect="light"
                style="margin-left: 5px"
              >
                {{ row.effective_state_label || stateLabel(row.effective_state) }}
              </el-tag>
              <div v-if="row.version_count > 1" class="t-grey t-sm">
                共 {{ row.version_count }} 个版本
              </div>
            </template>
          </el-table-column>

          <el-table-column label="上传人" width="130">
            <template #default="{ row }">
              <template v-if="row.current_uploaded_by?.name">
                <div>{{ row.current_uploaded_by.name }}</div>
                <div v-if="row.current_uploaded_by.employee_no" class="t-grey t-sm t-mono">
                  {{ row.current_uploaded_by.employee_no }}
                </div>
              </template>
              <span v-else class="t-grey t-sm">—</span>
              <div v-if="row.current_uploaded_at" class="t-grey t-sm">
                {{ formatDateTime(row.current_uploaded_at) }}
              </div>
            </template>
          </el-table-column>

          <el-table-column label="现在在谁手上" min-width="190">
            <template #default="{ row }">
              <!-- 只有确实有待签任务时才显示待签单位；
                   文件还在自己手上（未提交）不能显示成"等别人签"。 -->
              <div v-if="row.pending_count > 0" class="waits">
                <el-tag
                  v-for="u in row.pending_unit_labels"
                  :key="u"
                  size="small"
                  type="warning"
                  effect="light"
                >
                  {{ u }}
                </el-tag>
              </div>
              <el-tag v-else-if="row.workflow_finished" size="small" type="success" effect="plain">
                签认已完成
              </el-tag>
              <el-tag
                v-else-if="row.effective_state === 'PUBLISHED'"
                size="small"
                type="success"
                effect="plain"
              >
                已发布，无人待办
              </el-tag>
              <el-tag v-else size="small" type="info" effect="plain">未提交</el-tag>
              <div class="t-grey t-sm" style="margin-top: 3px">{{ locationText(row) }}</div>
            </template>
          </el-table-column>

          <el-table-column label="签认进度" width="100" align="center">
            <template #default="{ row }">
              <span class="t-mono t-sm">已签 {{ row.trace.length }}</span>
              <div v-if="row.pending_count > 0" class="t-amber t-sm">
                待签 {{ row.pending_count }}
              </div>
              <div v-if="row.awaiting_me" class="t-blue t-sm">待我签</div>
            </template>
          </el-table-column>
        </el-table>

        <div v-else class="empty t-grey">
          当前筛选范围内没有文件
        </div>
      </div>

      <!-- 七阶段责任总览 -->
      <div class="app-card pad" style="margin-top: 16px">
        <div class="sec-title">
          七阶段责任总览
          <span class="more" style="cursor: default">《管理流程》矩阵在系统里的落地</span>
        </div>

        <div class="board">
          <div v-for="b in board" :key="b.stage_code" class="bcard">
            <div class="bc-head">
              <span class="bc-stage">{{ b.stage_label || STAGE_LABEL[b.stage_code] }}</span>
              <el-tag
                v-if="b.inaround_count > 0"
                size="small"
                type="warning"
                effect="light"
              >
                {{ b.inaround_count }} 份在途
              </el-tag>
            </div>
            <div class="bc-primary">
              主办：<b>{{ UNIT_LABEL[b.primary_unit as UnitCode] || '—' }}</b>
            </div>
            <div class="bc-units">
              <span
                v-for="u in b.units_detail"
                :key="u.unit_code"
                class="bu"
                :class="{ own: u.responsibility === 'PRIMARY' }"
              >
                {{ u.unit_label || UNIT_LABEL[u.unit_code] }}
                <el-tag
                  :type="RESPONSIBILITY_TAG[u.responsibility] as never"
                  size="small"
                  effect="plain"
                  class="bu-tag"
                >
                  {{ u.responsibility_label || RESPONSIBILITY_LABEL[u.responsibility] }}
                </el-tag>
              </span>
            </div>
          </div>
        </div>
      </div>
    </template>

    <!-- ============ 签认轨迹抽屉 ============ -->
    <el-drawer v-model="detailOpen" title="文件追溯" size="640px">
      <template v-if="active">
        <div class="dt-title">{{ active.title }}</div>
        <div class="t-grey t-sm t-mono" style="margin-bottom: 14px">
          {{ active.doc_no || '无编号' }}
          · {{ active.stage_label || STAGE_LABEL[active.stage_code as never] }}
        </div>

        <el-descriptions :column="1" border size="small">
          <el-descriptions-item label="主办单位">
            <el-tag type="danger" size="small" effect="light">
              {{ active.primary_unit_label || '—' }}
            </el-tag>
            <span class="t-grey t-sm" style="margin-left: 8px">
              该阶段的主要责任单位，文件出问题由它负责
            </span>
          </el-descriptions-item>
          <el-descriptions-item label="当前状态">
            <el-tag :type="stateTag(active.effective_state)" size="small" effect="light">
              {{ active.effective_state_label || stateLabel(active.effective_state) }}
            </el-tag>
            <span class="t-mono t-sm" style="margin-left: 6px">
              {{ active.effective_version_no || '' }}
            </span>
          </el-descriptions-item>
          <el-descriptions-item label="现在在谁手上">
            <template v-if="active.pending_count > 0">
              <el-tag
                v-for="u in active.pending_unit_labels"
                :key="u"
                size="small"
                type="warning"
                effect="light"
                style="margin-right: 5px"
              >
                {{ u }}
              </el-tag>
            </template>
            <span v-else>{{ locationText(active) }}</span>
          </el-descriptions-item>
          <el-descriptions-item label="上传人">
            <template v-if="active.current_uploaded_by?.name">
              {{ active.current_uploaded_by.name }}
              <span v-if="active.current_uploaded_by.employee_no" class="t-mono t-grey">
                （{{ active.current_uploaded_by.employee_no }}）
              </span>
              <span v-if="active.current_uploaded_at" class="t-grey t-sm">
                · {{ formatDateTime(active.current_uploaded_at) }}
              </span>
            </template>
            <span v-else class="t-grey">—</span>
          </el-descriptions-item>
          <el-descriptions-item label="发布人">
            <template v-if="active.published_by?.name">
              {{ active.published_by.name }}
              <span v-if="active.published_by.employee_no" class="t-mono t-grey">
                （{{ active.published_by.employee_no }}）
              </span>
              <span v-if="active.published_at" class="t-grey t-sm">
                · {{ formatDateTime(active.published_at) }}
              </span>
            </template>
            <span v-else class="t-grey">尚未发布</span>
          </el-descriptions-item>
        </el-descriptions>

        <div class="sec-title" style="margin-top: 18px">
          签认轨迹
          <span class="more" style="cursor: default">{{ active.trace.length }} 条记录</span>
        </div>
        <el-timeline v-if="active.trace.length" style="padding-left: 4px">
          <el-timeline-item
            v-for="(t, i) in active.trace"
            :key="i"
            :type="t.node_code === 'CONFIRM' ? 'primary' : 'success'"
            size="normal"
          >
            <div class="tr-head">
              <b>{{ t.node_name || t.node_code }}</b>
              <el-tag size="small" effect="plain">{{ t.unit_label || '—' }}</el-tag>
              <span class="t-grey t-sm">
                {{ t.actor?.name || '—' }}
                <span v-if="t.actor?.employee_no" class="t-mono">（{{ t.actor.employee_no }}）</span>
                · {{ formatDateTime(t.acted_at) }}
              </span>
            </div>
            <div v-if="t.comment" class="tr-comment">{{ t.comment }}</div>
          </el-timeline-item>
        </el-timeline>
        <div v-else class="t-grey t-sm">
          该文件还没有签认记录（尚未提交，或提交前）。
        </div>
      </template>
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
  padding: 16px 22px;
}
.head-actions {
  margin-left: auto;
  display: flex;
  align-items: center;
  gap: 12px;
  flex: 0 0 auto;
}

/* ---------------- 概览 ---------------- */
.stats {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
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

.pad {
  padding: 16px 20px;
  margin-top: 16px;
}
.empty {
  padding: 40px;
  text-align: center;
}

.f-title {
  font-size: 13.5px;
  font-weight: 600;
  color: var(--ink);
}
.waits {
  display: flex;
  gap: 4px;
  flex-wrap: wrap;
}

/* ---------------- 七阶段责任总览 ---------------- */
.board {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(330px, 1fr));
  gap: 12px;
}
.bcard {
  border: 1px solid var(--line);
  border-radius: 6px;
  padding: 12px 14px;
  background: #fbfcfe;
}
.bc-head {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 7px;
}
.bc-stage {
  font-size: 14px;
  font-weight: 700;
  color: var(--ink);
}
.bc-primary {
  font-size: 12.5px;
  color: var(--ink-2);
  margin-bottom: 9px;
  padding-bottom: 8px;
  border-bottom: 1px dashed var(--line);
}
.bc-primary b {
  color: var(--red);
}
.bc-units {
  display: flex;
  flex-wrap: wrap;
  gap: 5px;
}
.bu {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  font-size: 11.5px;
  padding: 2px 7px;
  border-radius: 3px;
  background: #f1f4f8;
  color: var(--grey);
}
.bu.own {
  background: var(--red-soft);
  color: #8a2f26;
  font-weight: 700;
}
.bu-tag {
  transform: scale(0.85);
}

/* ---------------- 追溯抽屉 ---------------- */
.dt-title {
  font-size: 16px;
  font-weight: 700;
  margin-bottom: 3px;
}
.tr-head {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.tr-comment {
  margin-top: 6px;
  font-size: 12.5px;
  color: var(--ink-2);
  line-height: 1.75;
  background: #f7f9fc;
  border-radius: 4px;
  padding: 8px 11px;
}

@media (max-width: 1300px) {
  .stats {
    grid-template-columns: repeat(2, 1fr);
  }
}
</style>
