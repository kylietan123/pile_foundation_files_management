<script setup lang="ts">
/**
 * 试桩台账 —— 设计试桩 / 验收试桩阶段的阶段功能。
 * 列出试桩，回填实测承载力，与设计承载力做对比（实测 ≥ 设计 → 合格）。
 */
import { computed, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'

import { pileApi } from '@/api'
import { explainApiError } from '@/api/http'
import type { PileInfo } from '@/api/types'

const props = defineProps<{ projectId: string }>()

const loading = ref(false)
const error = ref<string | null>(null)
const piles = ref<PileInfo[]>([])

const editOpen = ref(false)
const editTarget = ref<PileInfo | null>(null)
const editForm = ref({
  actual_capacity: null as number | null,
  detection_method: '',
  review_status: '',
  review_note: '',
  remark: '',
})

const DETECTION_METHODS = ['静载', '低应变', '超声波', '钻芯']
const REVIEW_STATUS_LABEL: Record<string, string> = {
  PENDING: '待审查',
  APPROVED: '已通过',
  REJECTED: '未通过',
}

async function load() {
  loading.value = true
  error.value = null
  try {
    piles.value = await pileApi.list(props.projectId, true)
  } catch (e) {
    error.value = explainApiError(e)
  } finally {
    loading.value = false
  }
}

/** 是否合格：实测 ≥ 设计承载力 */
function verdict(p: PileInfo): 'passed' | 'failed' | 'untested' {
  if (p.actual_capacity == null || p.design_capacity == null) return 'untested'
  return p.actual_capacity >= p.design_capacity ? 'passed' : 'failed'
}

function ratio(p: PileInfo): string {
  if (p.actual_capacity == null || p.design_capacity == null) return '—'
  return (p.actual_capacity / p.design_capacity).toFixed(2)
}

const stats = computed(() => {
  const tested = piles.value.filter((p) => p.actual_capacity != null)
  const qualified = tested.filter(
    (p) => p.design_capacity != null && p.actual_capacity! >= p.design_capacity,
  )
  return { total: piles.value.length, tested: tested.length, qualified: qualified.length }
})

function openEdit(p: PileInfo) {
  editTarget.value = p
  editForm.value = {
    actual_capacity: p.actual_capacity ?? null,
    detection_method: p.detection_method || '',
    review_status: p.review_status || '',
    review_note: p.review_note || '',
    remark: p.remark || '',
  }
  editOpen.value = true
}

async function saveEdit() {
  if (!editTarget.value) return
  try {
    await pileApi.update(editTarget.value.id, {
      actual_capacity: editForm.value.actual_capacity,
      detection_method: editForm.value.detection_method || null,
      review_status: editForm.value.review_status || null,
      review_note: editForm.value.review_note || null,
      remark: editForm.value.remark || null,
    })
    ElMessage.success('已保存')
    editOpen.value = false
    await load()
  } catch (e) {
    ElMessage.error(explainApiError(e))
  }
}

onMounted(load)
</script>

<template>
  <div class="pile-ledger">
    <div class="app-card pad">
      <div class="sec-title">
        试桩台账
        <span class="more t-grey t-sm">
          试桩 {{ stats.total }} 根 · 已测 {{ stats.tested }} · 合格 {{ stats.qualified }}
        </span>
      </div>
      <p class="t-grey t-sm" style="margin: 4px 0 12px">
        实测承载力 ≥ 设计承载力即判为<b class="t-teal">合格</b>；点击「回填」记录静载试验实测值。
      </p>

      <el-alert v-if="error" :title="error" type="error" :closable="false" show-icon />
      <el-skeleton v-else-if="loading" :rows="5" animated />

      <el-table v-else :data="piles" size="small" style="width: 100%">
        <el-table-column prop="pile_no" label="桩号" min-width="130" />
        <el-table-column prop="pile_type_name" label="桩型" min-width="130">
          <template #default="{ row }">{{ row.pile_type_name || '—' }}</template>
        </el-table-column>
        <el-table-column prop="zone" label="分区" width="100">
          <template #default="{ row }">{{ row.zone || '—' }}</template>
        </el-table-column>
        <el-table-column prop="design_length" label="桩长(m)" width="90" align="right">
          <template #default="{ row }">{{ row.design_length ?? '—' }}</template>
        </el-table-column>
        <el-table-column prop="design_diameter" label="桩径(mm)" width="100" align="right">
          <template #default="{ row }">{{ row.design_diameter ?? '—' }}</template>
        </el-table-column>
        <el-table-column prop="design_capacity" label="设计承载力(kN)" width="130" align="right">
          <template #default="{ row }">{{ row.design_capacity ?? '—' }}</template>
        </el-table-column>
        <el-table-column prop="actual_capacity" label="实测承载力(kN)" width="130" align="right">
          <template #default="{ row }">
            <span :class="verdict(row) === 'failed' ? 't-red' : ''">
              {{ row.actual_capacity ?? '未测' }}
            </span>
          </template>
        </el-table-column>
        <el-table-column prop="detection_method" label="检测方法" width="110" align="center">
          <template #default="{ row }">{{ row.detection_method || '—' }}</template>
        </el-table-column>
        <el-table-column label="政府审查" width="110" align="center">
          <template #default="{ row }">
            <template v-if="row.review_status">
              <el-tag
                size="small"
                :type="row.review_status === 'APPROVED' ? 'success' : row.review_status === 'REJECTED' ? 'danger' : 'info'"
              >
                {{ REVIEW_STATUS_LABEL[row.review_status] || row.review_status }}
              </el-tag>
              <div v-if="row.review_note" class="t-grey t-sm">{{ row.review_note }}</div>
            </template>
            <span v-else class="t-grey t-sm">—</span>
          </template>
        </el-table-column>
        <el-table-column label="对比" width="110" align="center">
          <template #default="{ row }">
            <el-tag v-if="verdict(row) === 'untested'" size="small" type="info">未测</el-tag>
            <el-tag v-else-if="verdict(row) === 'passed'" size="small" type="success">
              合格 · {{ ratio(row) }}
            </el-tag>
            <el-tag v-else size="small" type="danger">不合格 · {{ ratio(row) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="备注" min-width="140">
          <template #default="{ row }">{{ row.remark || '—' }}</template>
        </el-table-column>
        <el-table-column label="操作" width="80" align="center">
          <template #default="{ row }">
            <el-button link size="small" type="primary" @click="openEdit(row)">回填</el-button>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <el-dialog v-model="editOpen" title="回填实测承载力" width="440px">
      <el-form label-width="110px">
        <el-form-item label="桩号">
          <span>{{ editTarget?.pile_no }}</span>
        </el-form-item>
        <el-form-item label="设计承载力">
          <span>{{ editTarget?.design_capacity ?? '—' }} kN</span>
        </el-form-item>
        <el-form-item label="实测承载力">
          <el-input-number v-model="editForm.actual_capacity" :min="0" :step="10" style="width: 100%" />
        </el-form-item>
        <el-form-item label="检测方法">
          <el-select v-model="editForm.detection_method" placeholder="选择检测方法" clearable style="width: 100%">
            <el-option v-for="m in DETECTION_METHODS" :key="m" :label="m" :value="m" />
          </el-select>
        </el-form-item>
        <el-form-item label="政府审查">
          <el-select v-model="editForm.review_status" placeholder="审查状态" clearable style="width: 100%">
            <el-option label="待审查" value="PENDING" />
            <el-option label="已通过" value="APPROVED" />
            <el-option label="未通过" value="REJECTED" />
          </el-select>
        </el-form-item>
        <el-form-item label="审查意见">
          <el-input v-model="editForm.review_note" placeholder="政府审查意见" />
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="editForm.remark" placeholder="如：静载试验合格 / 不合格原因" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="editOpen = false">取消</el-button>
        <el-button type="primary" @click="saveEdit">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.pad {
  padding: 16px 18px;
}
</style>
