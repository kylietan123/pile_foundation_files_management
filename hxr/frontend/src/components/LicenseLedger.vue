<script setup lang="ts">
/**
 * 证照台账 —— 前期调研阶段的阶段功能。
 * 列出证照（名称/编号/发证机关/发证日期/有效期），带有效期到期提醒。
 */
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'

import { licenseApi } from '@/api'
import { explainApiError } from '@/api/http'
import type { LicenseInfo } from '@/api/types'

const props = defineProps<{ projectId: string }>()

const loading = ref(false)
const error = ref<string | null>(null)
const list = ref<LicenseInfo[]>([])

const dialogOpen = ref(false)
const editingId = ref<string | null>(null)
const form = reactive({
  name: '',
  license_no: '',
  authority: '',
  issue_date: '' as string,
  valid_until: '' as string,
  remark: '',
})

/** 有效期状态：已过期 / 临近到期 / 有效 / 未填写 */
function validity(l: LicenseInfo): { tag: string; type: 'danger' | 'warning' | 'success' | 'info' } {
  if (!l.valid_until) return { tag: '未填写', type: 'info' }
  const d = new Date(l.valid_until)
  const now = new Date()
  const days = Math.ceil((d.getTime() - now.getTime()) / 86400000)
  if (days < 0) return { tag: '已过期', type: 'danger' }
  if (days <= 90) return { tag: `临近到期(${days}天)`, type: 'warning' }
  return { tag: '有效', type: 'success' }
}

async function load() {
  loading.value = true
  error.value = null
  try {
    list.value = await licenseApi.list(props.projectId)
  } catch (e) {
    error.value = explainApiError(e)
  } finally {
    loading.value = false
  }
}

function openCreate() {
  editingId.value = null
  form.name = ''
  form.license_no = ''
  form.authority = ''
  form.issue_date = ''
  form.valid_until = ''
  form.remark = ''
  dialogOpen.value = true
}

function openEdit(l: LicenseInfo) {
  editingId.value = l.id
  form.name = l.name
  form.license_no = l.license_no || ''
  form.authority = l.authority || ''
  form.issue_date = l.issue_date || ''
  form.valid_until = l.valid_until || ''
  form.remark = l.remark || ''
  dialogOpen.value = true
}

async function save() {
  if (!form.name.trim()) {
    ElMessage.warning('请填写证照名称')
    return
  }
  const body = {
    license_no: form.license_no || null,
    authority: form.authority || null,
    issue_date: form.issue_date || null,
    valid_until: form.valid_until || null,
    remark: form.remark || null,
  }
  try {
    if (editingId.value) {
      await licenseApi.update(editingId.value, body)
      ElMessage.success('已保存')
    } else {
      await licenseApi.create(props.projectId, { name: form.name.trim(), ...body })
      ElMessage.success('已新建')
    }
    dialogOpen.value = false
    await load()
  } catch (e) {
    ElMessage.error(explainApiError(e))
  }
}

async function remove(l: LicenseInfo) {
  try {
    await ElMessageBox.confirm(`确定删除证照「${l.name}」吗？`, '删除证照', {
      type: 'warning',
      confirmButtonText: '删除',
      cancelButtonText: '取消',
    })
  } catch {
    return
  }
  try {
    await licenseApi.delete(l.id)
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
      证照台账
      <span class="more t-grey t-sm">共 {{ list.length }} 项</span>
    </div>
    <div style="margin-bottom: 12px">
      <el-button type="primary" size="small" @click="openCreate">＋ 新建证照</el-button>
    </div>

    <el-alert v-if="error" :title="error" type="error" :closable="false" show-icon />
    <el-skeleton v-else-if="loading" :rows="4" animated />

    <el-table v-else :data="list" size="small" style="width: 100%">
      <el-table-column prop="name" label="证照名称" min-width="180" />
      <el-table-column prop="license_no" label="证照编号" min-width="160">
        <template #default="{ row }">{{ row.license_no || '—' }}</template>
      </el-table-column>
      <el-table-column prop="authority" label="发证机关" min-width="160">
        <template #default="{ row }">{{ row.authority || '—' }}</template>
      </el-table-column>
      <el-table-column prop="issue_date" label="发证日期" width="110">
        <template #default="{ row }">{{ row.issue_date || '—' }}</template>
      </el-table-column>
      <el-table-column prop="valid_until" label="有效期至" width="110">
        <template #default="{ row }">{{ row.valid_until || '—' }}</template>
      </el-table-column>
      <el-table-column label="状态" width="130" align="center">
        <template #default="{ row }">
          <el-tag size="small" :type="validity(row).type">{{ validity(row).tag }}</el-tag>
        </template>
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

    <el-dialog v-model="dialogOpen" :title="editingId ? '编辑证照' : '新建证照'" width="480px">
      <el-form label-width="100px">
        <el-form-item label="证照名称" required>
          <el-input v-model="form.name" :disabled="!!editingId" placeholder="如：项目立项批复文件" />
        </el-form-item>
        <el-form-item label="证照编号">
          <el-input v-model="form.license_no" placeholder="如：杭发改〔2024〕12号" />
        </el-form-item>
        <el-form-item label="发证机关">
          <el-input v-model="form.authority" placeholder="如：杭州市发改委" />
        </el-form-item>
        <el-form-item label="发证日期">
          <el-date-picker v-model="form.issue_date" type="date" value-format="YYYY-MM-DD" style="width: 100%" />
        </el-form-item>
        <el-form-item label="有效期至">
          <el-date-picker v-model="form.valid_until" type="date" value-format="YYYY-MM-DD" style="width: 100%" />
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
