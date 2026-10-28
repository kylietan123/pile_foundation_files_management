<script setup lang="ts">
/**
 * 监测点台账 —— 运维监测阶段的阶段功能。
 * 列出监测点（点号/监测项/预警阈值/最新值），按最新值 vs 阈值自动判预警。
 */
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'

import { monitoringApi } from '@/api'
import { explainApiError } from '@/api/http'
import type { MonitoringPointInfo } from '@/api/types'

const props = defineProps<{ projectId: string }>()

const loading = ref(false)
const error = ref<string | null>(null)
const list = ref<MonitoringPointInfo[]>([])

const dialogOpen = ref(false)
const editingId = ref<string | null>(null)
const form = reactive({
  point_no: '',
  monitor_item: '',
  threshold: null as number | null,
  latest_value: null as number | null,
  unit: '',
  last_measured_at: '' as string,
  remark: '',
})

const MONITOR_ITEMS = ['沉降', '水平位移', '地下水位', '轴力']

/** 预警状态：最新值 vs 阈值 */
function warning(p: MonitoringPointInfo): { tag: string; type: 'danger' | 'warning' | 'success' | 'info' } {
  if (p.latest_value == null || p.threshold == null) return { tag: '未设置', type: 'info' }
  if (p.latest_value >= p.threshold) return { tag: '超限', type: 'danger' }
  if (p.latest_value >= p.threshold * 0.8) return { tag: '预警', type: 'warning' }
  return { tag: '正常', type: 'success' }
}

const stats = computed(() => {
  const over = list.value.filter((p) => warning(p).type === 'danger').length
  const warn = list.value.filter((p) => warning(p).type === 'warning').length
  return { total: list.value.length, over, warn }
})

async function load() {
  loading.value = true
  error.value = null
  try {
    list.value = await monitoringApi.list(props.projectId)
  } catch (e) {
    error.value = explainApiError(e)
  } finally {
    loading.value = false
  }
}

function openCreate() {
  editingId.value = null
  form.point_no = ''
  form.monitor_item = ''
  form.threshold = null
  form.latest_value = null
  form.unit = ''
  form.last_measured_at = ''
  form.remark = ''
  dialogOpen.value = true
}

function openEdit(p: MonitoringPointInfo) {
  editingId.value = p.id
  form.point_no = p.point_no
  form.monitor_item = p.monitor_item || ''
  form.threshold = p.threshold ?? null
  form.latest_value = p.latest_value ?? null
  form.unit = p.unit || ''
  form.last_measured_at = p.last_measured_at || ''
  form.remark = p.remark || ''
  dialogOpen.value = true
}

async function save() {
  if (!form.point_no.trim()) {
    ElMessage.warning('请填写点号')
    return
  }
  const body = {
    monitor_item: form.monitor_item || null,
    threshold: form.threshold,
    latest_value: form.latest_value,
    unit: form.unit || null,
    last_measured_at: form.last_measured_at || null,
    remark: form.remark || null,
  }
  try {
    if (editingId.value) {
      await monitoringApi.update(editingId.value, body)
      ElMessage.success('已保存')
    } else {
      await monitoringApi.create(props.projectId, { point_no: form.point_no.trim(), ...body })
      ElMessage.success('已新建')
    }
    dialogOpen.value = false
    await load()
  } catch (e) {
    ElMessage.error(explainApiError(e))
  }
}

async function remove(p: MonitoringPointInfo) {
  try {
    await ElMessageBox.confirm(`确定删除监测点「${p.point_no}」吗？`, '删除监测点', {
      type: 'warning',
      confirmButtonText: '删除',
      cancelButtonText: '取消',
    })
  } catch {
    return
  }
  try {
    await monitoringApi.delete(p.id)
    ElMessage.success('已删除')
    await load()
  } catch (e) {
    ElMessage.error(explainApiError(e))
  }
}

onMounted(load)
</script>

<template>
  <div class="app-card pad">
    <div class="sec-title">
      监测点台账
      <span class="more t-grey t-sm">
        共 {{ stats.total }} 点 · <span class="t-red">超限 {{ stats.over }}</span> ·
        <span class="t-amber">预警 {{ stats.warn }}</span>
      </span>
    </div>
    <div style="margin-bottom: 12px">
      <el-button type="primary" size="small" @click="openCreate">＋ 新建监测点</el-button>
    </div>

    <el-alert v-if="error" :title="error" type="error" :closable="false" show-icon />
    <el-skeleton v-else-if="loading" :rows="4" animated />

    <el-table v-else :data="list" size="small" style="width: 100%">
      <el-table-column prop="point_no" label="点号" min-width="100" />
      <el-table-column prop="monitor_item" label="监测项" width="110">
        <template #default="{ row }">{{ row.monitor_item || '—' }}</template>
      </el-table-column>
      <el-table-column prop="threshold" label="预警阈值" width="100" align="right">
        <template #default="{ row }">{{ row.threshold ?? '—' }}</template>
      </el-table-column>
      <el-table-column prop="latest_value" label="最新值" width="100" align="right">
        <template #default="{ row }">
          <span :class="warning(row).type === 'danger' ? 't-red' : warning(row).type === 'warning' ? 't-amber' : ''">
            {{ row.latest_value ?? '—' }}
          </span>
        </template>
      </el-table-column>
      <el-table-column prop="unit" label="单位" width="70">
        <template #default="{ row }">{{ row.unit || '—' }}</template>
      </el-table-column>
      <el-table-column label="预警状态" width="100" align="center">
        <template #default="{ row }">
          <el-tag size="small" :type="warning(row).type">{{ warning(row).tag }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="last_measured_at" label="最近测量" width="110">
        <template #default="{ row }">{{ row.last_measured_at || '—' }}</template>
      </el-table-column>
      <el-table-column prop="remark" label="备注" min-width="120">
        <template #default="{ row }">{{ row.remark || '—' }}</template>
      </el-table-column>
      <el-table-column label="操作" width="130" align="center">
        <template #default="{ row }">
          <el-button link size="small" type="primary" @click="openEdit(row)">编辑</el-button>
          <el-button link size="small" type="danger" @click="remove(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog v-model="dialogOpen" :title="editingId ? '编辑监测点' : '新建监测点'" width="480px">
      <el-form label-width="100px">
        <el-form-item label="点号" required>
          <el-input v-model="form.point_no" :disabled="!!editingId" placeholder="如 CJ01" />
        </el-form-item>
        <el-form-item label="监测项">
          <el-select v-model="form.monitor_item" filterable allow-create placeholder="选择或输入监测项" style="width: 100%">
            <el-option v-for="m in MONITOR_ITEMS" :key="m" :label="m" :value="m" />
          </el-select>
        </el-form-item>
        <el-form-item label="预警阈值">
          <el-input-number v-model="form.threshold" :step="1" style="width: 100%" />
        </el-form-item>
        <el-form-item label="最新值">
          <el-input-number v-model="form.latest_value" :step="1" style="width: 100%" />
        </el-form-item>
        <el-form-item label="单位">
          <el-input v-model="form.unit" placeholder="如 mm / m" />
        </el-form-item>
        <el-form-item label="最近测量">
          <el-date-picker v-model="form.last_measured_at" type="date" value-format="YYYY-MM-DD" style="width: 100%" />
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="form.remark" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogOpen = false">取消</el-button>
        <el-button type="primary" @click="save">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.pad {
  padding: 16px 18px;
}
</style>
