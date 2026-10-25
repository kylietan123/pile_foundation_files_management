<script setup lang="ts">
/**
 * 钻孔台账 —— 地质勘察阶段的阶段功能。
 * 列出钻孔（孔号 / 坐标 / 孔深 / 标高 / 勘察日期），可新建、编辑、删除。
 */
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'

import { boreholeApi } from '@/api'
import { explainApiError } from '@/api/http'
import type { BoreholeInfo } from '@/api/types'

const props = defineProps<{ projectId: string }>()

const loading = ref(false)
const error = ref<string | null>(null)
const list = ref<BoreholeInfo[]>([])

const dialogOpen = ref(false)
const editingId = ref<string | null>(null)
const form = reactive({
  borehole_no: '',
  x: null as number | null,
  y: null as number | null,
  depth: null as number | null,
  elevation: null as number | null,
  survey_date: '' as string,
  remark: '',
})

async function load() {
  loading.value = true
  error.value = null
  try {
    list.value = await boreholeApi.list(props.projectId)
  } catch (e) {
    error.value = explainApiError(e)
  } finally {
    loading.value = false
  }
}

function openCreate() {
  editingId.value = null
  form.borehole_no = ''
  form.x = null
  form.y = null
  form.depth = null
  form.elevation = null
  form.survey_date = ''
  form.remark = ''
  dialogOpen.value = true
}

function openEdit(b: BoreholeInfo) {
  editingId.value = b.id
  form.borehole_no = b.borehole_no
  form.x = b.x ?? null
  form.y = b.y ?? null
  form.depth = b.depth ?? null
  form.elevation = b.elevation ?? null
  form.survey_date = b.survey_date || ''
  form.remark = b.remark || ''
  dialogOpen.value = true
}

async function save() {
  if (!form.borehole_no.trim()) {
    ElMessage.warning('请填写孔号')
    return
  }
  const body = {
    x: form.x,
    y: form.y,
    depth: form.depth,
    elevation: form.elevation,
    survey_date: form.survey_date || null,
    remark: form.remark || null,
  }
  try {
    if (editingId.value) {
      await boreholeApi.update(editingId.value, body)
      ElMessage.success('已保存')
    } else {
      await boreholeApi.create(props.projectId, { borehole_no: form.borehole_no.trim(), ...body })
      ElMessage.success('已新建')
    }
    dialogOpen.value = false
    await load()
  } catch (e) {
    ElMessage.error(explainApiError(e))
  }
}

async function remove(b: BoreholeInfo) {
  try {
    await ElMessageBox.confirm(`确定删除钻孔「${b.borehole_no}」吗？`, '删除钻孔', {
      type: 'warning',
      confirmButtonText: '删除',
      cancelButtonText: '取消',
    })
  } catch {
    return
  }
  try {
    await boreholeApi.delete(b.id)
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
      钻孔台账
      <span class="more t-grey t-sm">共 {{ list.length }} 个钻孔</span>
    </div>
    <div style="margin-bottom: 12px">
      <el-button type="primary" size="small" @click="openCreate">＋ 新建钻孔</el-button>
    </div>

    <el-alert v-if="error" :title="error" type="error" :closable="false" show-icon />
    <el-skeleton v-else-if="loading" :rows="4" animated />

    <el-table v-else :data="list" size="small" style="width: 100%">
      <el-table-column prop="borehole_no" label="孔号" min-width="100" />
      <el-table-column prop="x" label="坐标 X (m)" width="110" align="right">
        <template #default="{ row }">{{ row.x ?? '—' }}</template>
      </el-table-column>
      <el-table-column prop="y" label="坐标 Y (m)" width="110" align="right">
        <template #default="{ row }">{{ row.y ?? '—' }}</template>
      </el-table-column>
      <el-table-column prop="depth" label="孔深 (m)" width="100" align="right">
        <template #default="{ row }">{{ row.depth ?? '—' }}</template>
      </el-table-column>
      <el-table-column prop="elevation" label="孔口标高 (m)" width="120" align="right">
        <template #default="{ row }">{{ row.elevation ?? '—' }}</template>
      </el-table-column>
      <el-table-column prop="survey_date" label="勘察日期" width="120">
        <template #default="{ row }">{{ row.survey_date || '—' }}</template>
      </el-table-column>
      <el-table-column prop="remark" label="备注" min-width="160">
        <template #default="{ row }">{{ row.remark || '—' }}</template>
      </el-table-column>
      <el-table-column label="操作" width="130" align="center">
        <template #default="{ row }">
          <el-button link size="small" type="primary" @click="openEdit(row)">编辑</el-button>
          <el-button link size="small" type="danger" @click="remove(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog v-model="dialogOpen" :title="editingId ? '编辑钻孔' : '新建钻孔'" width="480px">
      <el-form label-width="100px">
        <el-form-item label="孔号" required>
          <el-input v-model="form.borehole_no" :disabled="!!editingId" placeholder="如 ZK01" />
        </el-form-item>
        <el-form-item label="坐标 X (m)">
          <el-input-number v-model="form.x" :step="0.1" style="width: 100%" />
        </el-form-item>
        <el-form-item label="坐标 Y (m)">
          <el-input-number v-model="form.y" :step="0.1" style="width: 100%" />
        </el-form-item>
        <el-form-item label="孔深 (m)">
          <el-input-number v-model="form.depth" :step="0.5" style="width: 100%" />
        </el-form-item>
        <el-form-item label="孔口标高 (m)">
          <el-input-number v-model="form.elevation" :step="0.1" style="width: 100%" />
        </el-form-item>
        <el-form-item label="勘察日期">
          <el-date-picker v-model="form.survey_date" type="date" value-format="YYYY-MM-DD" style="width: 100%" />
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="form.remark" placeholder="如：淤泥质黏土至中风化岩" />
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
