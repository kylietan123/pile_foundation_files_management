<script setup lang="ts">
/**
 * 阶段待上传清单：把标准文档清单变成可操作的上传清单。
 *
 * 每一条文档可：上传 / 更新版本 / 标记「本项目不需要」(带原因) / 标记「暂未上传」(带原因)。
 */
import { computed, onMounted, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'

import { checklistApi } from '@/api'
import { explainApiError } from '@/api/http'
import type { ChecklistItem } from '@/api/types'

const props = defineProps<{
  projectId: string
  stage: string | null
}>()

const emit = defineEmits<{ (e: 'changed'): void }>()

const loading = ref(false)
const error = ref<string | null>(null)
const items = ref<ChecklistItem[]>([])

const fileInput = ref<HTMLInputElement | null>(null)
const uploadingCode = ref<string | null>(null)

const stats = computed(() => {
  const n = items.value.length
  const uploaded = items.value.filter((i) => i.status === 'UPLOADED').length
  const notRequired = items.value.filter((i) => i.status === 'NOT_REQUIRED').length
  return { n, uploaded, notRequired, pending: n - uploaded - notRequired }
})

async function load() {
  if (!props.stage) {
    items.value = []
    return
  }
  loading.value = true
  error.value = null
  try {
    items.value = await checklistApi.list(props.projectId, props.stage)
  } catch (e) {
    error.value = explainApiError(e)
  } finally {
    loading.value = false
  }
}

function pickFile(code: string) {
  uploadingCode.value = code
  fileInput.value?.click()
}

async function onFileChange(e: Event) {
  const input = e.target as HTMLInputElement
  const file = input.files?.[0]
  const code = uploadingCode.value
  input.value = ''
  uploadingCode.value = null
  if (!file || !code) return
  try {
    await checklistApi.upload(props.projectId, code, file)
    ElMessage.success('上传成功')
    emit('changed')
    await load()
  } catch (err) {
    ElMessage.error(explainApiError(err))
  }
}

async function setStatus(code: string, status: 'PENDING' | 'NOT_REQUIRED', reason: string | null) {
  try {
    await checklistApi.setStatus(props.projectId, code, { status, reason })
    emit('changed')
    await load()
  } catch (err) {
    ElMessage.error(explainApiError(err))
  }
}

async function markNotRequired(code: string) {
  try {
    const { value } = await ElMessageBox.prompt('请填写本项目不需要上传的原因', '标记「不需要」', {
      inputPlaceholder: '例如：本项目为灌注桩，无静载试验要求',
      confirmButtonText: '确定',
      cancelButtonText: '取消',
    })
    await setStatus(code, 'NOT_REQUIRED', value || null)
  } catch {
    /* 用户取消 */
  }
}

async function markPending(code: string) {
  try {
    const { value } = await ElMessageBox.prompt('请填写现阶段还未上传的原因', '标记「暂未上传」', {
      inputPlaceholder: '例如：图纸尚未完成，预计下周上传',
      confirmButtonText: '确定',
      cancelButtonText: '取消',
    })
    await setStatus(code, 'PENDING', value || null)
  } catch {
    /* 用户取消 */
  }
}

function statusTag(status: ChecklistItem['status']) {
  if (status === 'UPLOADED') return 'success'
  if (status === 'NOT_REQUIRED') return 'info'
  return 'warning'
}

function statusLabel(status: ChecklistItem['status']) {
  if (status === 'UPLOADED') return '已上传'
  if (status === 'NOT_REQUIRED') return '不需要'
  return '待上传'
}

onMounted(load)
watch(() => props.stage, load)
</script>

<template>
  <div v-if="stage" class="checklist app-card">
    <div class="cl-head">
      <span class="cl-title">本阶段待上传清单</span>
      <span class="cl-stats t-grey t-sm">
        共 {{ stats.n }} 项 · 已上传 {{ stats.uploaded }} · 不需要 {{ stats.notRequired }} ·
        待上传 {{ stats.pending }}
      </span>
    </div>

    <el-alert v-if="error" :title="error" type="error" :closable="false" show-icon />
    <el-skeleton v-else-if="loading" :rows="4" animated />

    <div v-else-if="items.length" class="cl-list">
      <div v-for="it in items" :key="it.doc_code" class="cl-row">
        <div class="cl-info">
          <div class="cl-name">
            <span class="cl-code t-mono">{{ it.doc_code }}</span>
            {{ it.doc_name }}
          </div>
          <div class="cl-meta t-grey t-sm">
            <el-tag size="small" effect="plain">{{ it.responsible_unit_name }}</el-tag>
            <el-tag size="small" effect="plain" type="info">{{ it.file_formats }}</el-tag>
            <el-tag size="small" :type="statusTag(it.status)" effect="light">{{ statusLabel(it.status) }}</el-tag>
            <span v-if="it.reason" class="cl-reason">原因：{{ it.reason }}</span>
          </div>
        </div>

        <div class="cl-actions">
          <template v-if="it.status !== 'UPLOADED'">
            <el-button size="small" type="primary" plain @click="pickFile(it.doc_code)">上传</el-button>
            <el-button size="small" @click="markPending(it.doc_code)">暂未上传</el-button>
            <el-button size="small" @click="markNotRequired(it.doc_code)">不需要</el-button>
          </template>
          <template v-else>
            <el-button size="small" type="primary" plain @click="pickFile(it.doc_code)">更新</el-button>
          </template>
          <el-button
            v-if="it.status === 'NOT_REQUIRED'"
            size="small"
            text
            type="primary"
            @click="setStatus(it.doc_code, 'PENDING', null)"
          >
            改为待上传
          </el-button>
        </div>
      </div>
    </div>

    <div v-else class="t-grey t-sm" style="padding: 12px 0">本阶段暂无标准清单条目。</div>

    <input ref="fileInput" type="file" hidden @change="onFileChange" />
  </div>
</template>

<style scoped>
.checklist {
  padding: 14px 18px;
  margin-bottom: 16px;
}
.cl-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  margin-bottom: 10px;
}
.cl-title {
  font-size: 15px;
  font-weight: 700;
}
.cl-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 10px 0;
  border-top: 1px dashed #eef2f7;
}
.cl-info {
  min-width: 0;
  flex: 1;
}
.cl-name {
  font-size: 14px;
}
.cl-code {
  color: #1e6fd9;
  font-size: 12px;
  margin-right: 6px;
}
.cl-meta {
  margin-top: 3px;
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}
.cl-reason {
  color: #b45309;
}
.cl-actions {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  gap: 4px;
}
</style>
