<script setup lang="ts">
/**
 * 我的工作 —— 跨项目的交办事项。
 *
 * **一个人同时参与多个项目，所以待办必须跨项目聚合**，
 * 否则每天要一个项目一个项目点进去看到底有什么要处理。
 *
 * 三类，按紧迫度排序：
 *   1 等我签认 —— 别人提交了卡在我这里，**不动手就拖住别人**
 *   2 被退回   —— 我提交的被打回，需要我改后重交
 *   3 我经手在途 —— 知悉用，不必动手
 */
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'

import { workbenchApi } from '@/api'
import { explainApiError } from '@/api/http'
import type { WorkItem, Workbench } from '@/api/types'
import { STAGE_LABEL, UNIT_LABEL, UnitCode } from '@/api/types'
import { formatDateTime } from '@/utils/format'

const router = useRouter()

const loading = ref(false)
const error = ref<string | null>(null)
const wb = ref<Workbench | null>(null)

/** 待我处理的 tab */
const activeTab = ref<'awaiting' | 'returned' | 'inflight'>('awaiting')

async function load() {
  loading.value = true
  error.value = null
  try {
    wb.value = await workbenchApi.myWork()
    // 没有待签但有被退回的，自动切到被退回那一栏
    if (!wb.value.awaiting_count && wb.value.returned_count) {
      activeTab.value = 'returned'
    }
  } catch (e) {
    error.value = explainApiError(e)
  } finally {
    loading.value = false
  }
}

onMounted(load)

/** 去处理：跳到该项目的台账页（在那里能看原文并签认） */
function goHandle(it: WorkItem) {
  router.push({ name: 'ledger', params: { id: it.project_id } })
}

/** 去项目总览 */
function goProject(it: WorkItem) {
  router.push({ name: 'project-detail', params: { id: it.project_id } })
}

const stageName = (s?: string | null) =>
  s ? STAGE_LABEL[s as never] || s : '—'

const unitName = (u?: string | null, label?: string | null) =>
  label || (u ? UNIT_LABEL[u as UnitCode] || u : '—')

/** 到期提醒的措辞 */
function dueText(it: WorkItem): string {
  if (it.overdue) return `已逾期`
  if (it.days_left === null || it.days_left === undefined) return '无期限'
  if (it.days_left <= 0) return '今天到期'
  return `剩 ${it.days_left} 天`
}

/** 当前 tab 的列表 */
const currentList = computed<WorkItem[]>(() => {
  if (!wb.value) return []
  if (activeTab.value === 'awaiting') return wb.value.awaiting
  if (activeTab.value === 'returned') return wb.value.returned
  return wb.value.inflight
})
</script>

<template>
  <div class="page">
    <!-- 顶部 -->
    <div class="head app-card">
      <div>
        <div class="sec-title" style="margin-bottom: 10px">
          我的工作
          <span class="more" style="cursor: default">跨项目汇总</span>
        </div>
        <p class="t-grey t-sm" style="margin: 0">
          一个人往往同时参与多个项目，所以待办在这里<b>跨项目汇总</b>。
          <b class="t-amber">「等我签认」排在最前 —— 不动手就会拖住别人。</b>
        </p>
      </div>
      <div class="head-actions">
        <el-button size="small" @click="load">刷新</el-button>
      </div>
    </div>

    <!-- 概览 -->
    <div class="stats">
      <div
        class="stat app-card"
        :class="{ alert: (wb?.awaiting_count ?? 0) > 0 }"
        @click="activeTab = 'awaiting'"
      >
        <div class="lab">等我签认</div>
        <div class="val" :class="(wb?.awaiting_count ?? 0) > 0 ? 't-blue' : 't-grey'">
          {{ wb?.awaiting_count ?? 0 }}
        </div>
        <div class="sub">别人在等我</div>
      </div>
      <div
        class="stat app-card"
        :class="{ alert: (wb?.returned_count ?? 0) > 0 }"
        @click="activeTab = 'returned'"
      >
        <div class="lab">被退回</div>
        <div class="val" :class="(wb?.returned_count ?? 0) > 0 ? 't-amber' : 't-grey'">
          {{ wb?.returned_count ?? 0 }}
        </div>
        <div class="sub">需要我修改后重交</div>
      </div>
      <div class="stat app-card" @click="activeTab = 'inflight'">
        <div class="lab">我经手在途</div>
        <div class="val t-grey">{{ wb?.inflight_count ?? 0 }}</div>
        <div class="sub">知悉用，不必动手</div>
      </div>
      <div class="stat app-card" :class="{ alert: (wb?.overdue_count ?? 0) > 0 }">
        <div class="lab">逾期</div>
        <div class="val" :class="(wb?.overdue_count ?? 0) > 0 ? 't-red' : 't-grey'">
          {{ wb?.overdue_count ?? 0 }}
        </div>
        <div class="sub">请优先处理</div>
      </div>
    </div>

    <el-skeleton v-if="loading" :rows="8" animated style="margin-top: 16px" />
    <el-alert v-else-if="error" :title="error" type="error" show-icon :closable="false" />
    <el-alert
      v-else-if="!wb?.awaiting_count && !wb?.returned_count"
      type="success"
      show-icon
      :closable="false"
      style="margin-top: 16px"
      title="当前没有需要你动手的事"
    >
      <div style="font-size: 12.5px; line-height: 1.7">
        没有等你签认的文件，也没有被退回的文件。
        你经手且仍在流转的文件在「我经手在途」里，仅供知悉。
      </div>
    </el-alert>

    <div v-else class="app-card pad">
      <el-tabs v-model="activeTab">
        <el-tab-pane :label="`等我签认（${wb?.awaiting_count ?? 0}）`" name="awaiting" />
        <el-tab-pane :label="`被退回（${wb?.returned_count ?? 0}）`" name="returned" />
        <el-tab-pane :label="`我经手在途（${wb?.inflight_count ?? 0}）`" name="inflight" />
      </el-tabs>

      <el-table
        v-if="currentList.length"
        :data="currentList"
        size="small"
        style="width: 100%"
      >
        <el-table-column label="项目" min-width="140">
          <template #default="{ row }">
            <a class="t-blue link" @click="goProject(row)">
              {{ row.project_short_name || row.project_name }}
            </a>
            <div class="t-grey t-sm">{{ stageName(row.stage_code) }}</div>
          </template>
        </el-table-column>

        <el-table-column label="文件" min-width="220">
          <template #default="{ row }">
            <div class="f-title">{{ row.title || '—' }}</div>
            <div class="t-grey t-sm t-mono">
              {{ row.doc_no || '无编号' }}
              <template v-if="row.version_no"> · {{ row.version_no }}</template>
              <template v-if="row.version_state_label">
                · {{ row.version_state_label }}
              </template>
            </div>
          </template>
        </el-table-column>

        <!-- 等我签认：显示是谁提交的、我以什么单位签 -->
        <template v-if="activeTab === 'awaiting'">
          <el-table-column label="提交人" width="130">
            <template #default="{ row }">
              <div>{{ row.submitted_by || '—' }}</div>
              <div v-if="row.submitted_by_no" class="t-grey t-sm t-mono">
                {{ row.submitted_by_no }}
              </div>
            </template>
          </el-table-column>
          <el-table-column label="我以何身份签" width="130">
            <template #default="{ row }">
              <el-tag size="small" type="warning" effect="light">
                {{ unitName(row.my_unit, row.my_unit_label) }}
              </el-tag>
              <div class="t-grey t-sm">{{ row.node_name || row.node_code }}</div>
            </template>
          </el-table-column>
          <el-table-column label="期限" width="110">
            <template #default="{ row }">
              <span :class="row.overdue ? 't-red' : ''">{{ dueText(row) }}</span>
              <div v-if="row.due_at" class="t-grey t-sm">{{ formatDateTime(row.due_at) }}</div>
            </template>
          </el-table-column>
        </template>

        <!-- 被退回：说明要做什么 -->
        <template v-else-if="activeTab === 'returned'">
          <el-table-column label="需要我做" min-width="180">
            <template #default>
              <span class="t-amber">内容被退回，修改后重新提交签认</span>
            </template>
          </el-table-column>
          <el-table-column label="上次提交" width="150">
            <template #default="{ row }">
              <span class="t-grey t-sm">{{ formatDateTime(row.submitted_at) }}</span>
            </template>
          </el-table-column>
        </template>

        <!-- 在途：显示卡在哪个单位 -->
        <template v-else>
          <el-table-column label="现在在谁手上" min-width="190">
            <template #default="{ row }">
              <el-tag
                v-for="u in row.pending_unit_labels || []"
                :key="u"
                size="small"
                type="info"
                effect="plain"
                style="margin-right: 4px"
              >
                {{ u }}
              </el-tag>
              <span v-if="!(row.pending_unit_labels || []).length" class="t-grey t-sm">
                流转中
              </span>
            </template>
          </el-table-column>
          <el-table-column label="提交时间" width="150">
            <template #default="{ row }">
              <span class="t-grey t-sm">{{ formatDateTime(row.submitted_at) }}</span>
            </template>
          </el-table-column>
        </template>

        <el-table-column label="操作" width="100" align="center">
          <template #default="{ row }">
            <el-button
              v-if="activeTab !== 'inflight'"
              link
              type="primary"
              size="small"
              @click="goHandle(row)"
            >
              去处理 →
            </el-button>
            <el-button v-else link size="small" @click="goHandle(row)">查看</el-button>
          </template>
        </el-table-column>
      </el-table>

      <div v-else class="empty t-grey">
        <template v-if="activeTab === 'awaiting'">没有等你签认的文件</template>
        <template v-else-if="activeTab === 'returned'">没有被退回的文件</template>
        <template v-else>没有正在流转的文件</template>
      </div>
    </div>
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
  flex: 0 0 auto;
}

.stats {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 14px;
  margin-top: 14px;
}
.stat {
  padding: 13px 16px;
  cursor: pointer;
  transition: border-color 0.15s;
}
.stat:hover {
  border-color: var(--blue);
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
  padding: 8px 20px 18px;
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
.link {
  cursor: pointer;
  font-weight: 600;
}

@media (max-width: 1300px) {
  .stats {
    grid-template-columns: repeat(2, 1fr);
  }
}
</style>
