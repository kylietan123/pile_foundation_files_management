<script setup lang="ts">
/**
 * 文件与版本管理 —— 版本状态机的界面。
 *
 * 这里体现四条铁律：
 *   1 未发布版本不可被下游引用 —— 列表上明确区分"有效版本"与其他版本
 *   2 不允许同时存在两个审批中版本 —— 上传按钮会在有审批中版本时被拦
 *   3 已发布不可回退 —— 已发布版本没有"编辑"，只有"发起修订"
 *   4 同一时刻最多一个已发布版本 —— 每个文件只标记一个"当前有效"
 *
 * 操作按钮由后端下发的 available_actions 驱动，
 * 前端不自己判断状态机 —— 避免前后端规则不一致。
 */
import { computed, nextTick, onMounted, reactive, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import type { UploadFile } from 'element-plus'

import { checklistApi, designInputApi, dictApi, documentApi } from '@/api'
import { explainApiError } from '@/api/http'
import type { ChecklistItem, DictItem, DocumentInfo, DocumentVersionInfo, StageCode, WorkflowTrace } from '@/api/types'
import {
  DOCUMENT_STATE_LABEL,
  DOCUMENT_STATE_TAG,
  NODE_LABEL,
  SECRET_LEVEL_LABEL,
  STAGE_LABEL,
  TASK_ACTION_LABEL,
} from '@/api/types'
import { useAuthStore } from '@/stores/auth'
import StageContextBar from '@/components/StageContextBar.vue'
import StageChecklist from '@/components/StageChecklist.vue'
import { formatDate, formatDateTime } from '@/utils/format'

const route = useRoute()
const auth = useAuthStore()
const projectId = computed(() => route.params.id as string)
const stage = computed(() => (route.query.stage as string) || null)

const loading = ref(false)
const error = ref<string | null>(null)
const docs = ref<DocumentInfo[]>([])
const docTypes = ref<DictItem[]>([])

/** 详情抽屉 */
const detailOpen = ref(false)
const detailDoc = ref<DocumentInfo | null>(null)
const trace = ref<WorkflowTrace | null>(null)
const traceLoading = ref(false)
/** 当前正在看哪个版本的审批轨迹 */
const traceVersionId = ref<string | null>(null)

/** 新建文档对话框 */
const createOpen = ref(false)
const createForm = reactive({
  title: '',
  titleSelect: '', // 下拉选择：清单 doc_code / 'OTHER' / ''
  doc_code: null as string | null,
  doc_no: '',
  category_id: '' as string | null,
  discipline: '结构',
  secret_level: 'INTERNAL',
})

/** 本阶段标准清单（用于「文件名称」下拉） */
const catalogOptions = ref<ChecklistItem[]>([])

function matchCategory(formats: string): string | null {
  if (!formats) return null
  const hit = docTypes.value.find((t) => t.name.includes(formats) || formats.includes(t.name))
  return hit ? hit.id : null
}

function onTitleSelect() {
  if (createForm.titleSelect === 'OTHER' || !createForm.titleSelect) {
    createForm.doc_code = null
    createForm.doc_no = ''
    createForm.title = ''
    return
  }
  const item = catalogOptions.value.find((i) => i.doc_code === createForm.titleSelect)
  if (!item) return
  createForm.title = item.doc_name
  createForm.doc_code = item.doc_code
  createForm.doc_no = item.doc_code
  createForm.category_id = matchCategory(item.file_formats)
}

/** 上传版本对话框 */
const uploadOpen = ref(false)
const uploadTarget = ref<DocumentInfo | null>(null)
const uploadFile = ref<File | null>(null)
const uploadSummary = ref('')

/** 新建对话框里选中的文件（可选，选了就创建后直接上传第一个版本） */
const createFile = ref<File | null>(null)

function onCreateFileChange(f: UploadFile) {
  createFile.value = (f.raw as File) ?? null
}

/** ---------------- 删除（验证码确认） ---------------- */
const deleteTarget = ref<DocumentInfo | null>(null)
const captchaCode = ref('')
const captchaInput = ref('')
const captchaCanvas = ref<HTMLCanvasElement | null>(null)

const deleteOpen = computed({
  get: () => deleteTarget.value !== null,
  set: (v: boolean) => {
    if (!v) deleteTarget.value = null
  },
})

function rand(n: number) {
  return Math.floor(Math.random() * n)
}

function drawCaptcha() {
  const canvas = captchaCanvas.value
  if (!canvas) return
  const ctx = canvas.getContext('2d')
  if (!ctx) return
  const w = canvas.width
  const h = canvas.height
  ctx.clearRect(0, 0, w, h)
  ctx.fillStyle = '#eef2f7'
  ctx.fillRect(0, 0, w, h)
  for (let i = 0; i < 30; i++) {
    ctx.fillStyle = `rgba(${rand(180)},${rand(180)},${rand(180)},0.35)`
    ctx.fillRect(rand(w), rand(h), 2, 2)
  }
  for (let i = 0; i < 5; i++) {
    ctx.strokeStyle = `rgba(${rand(160)},${rand(160)},${rand(160)},0.5)`
    ctx.beginPath()
    ctx.moveTo(rand(w), rand(h))
    ctx.lineTo(rand(w), rand(h))
    ctx.stroke()
  }
  ctx.font = 'bold 28px Consolas, monospace'
  ctx.textAlign = 'center'
  ctx.textBaseline = 'middle'
  const step = w / (captchaCode.value.length + 1)
  captchaCode.value.split('').forEach((ch, i) => {
    ctx.save()
    ctx.translate(step * (i + 1), h / 2)
    ctx.rotate((Math.random() - 0.5) * 0.7)
    ctx.fillStyle = `rgb(${rand(120)},${rand(120)},${rand(120)})`
    ctx.fillText(ch, 0, 0)
    ctx.restore()
  })
}

function genCaptcha() {
  let code = ''
  for (let i = 0; i < 4; i++) code += String(rand(10))
  captchaCode.value = code
  captchaInput.value = ''
  nextTick(() => drawCaptcha())
}

function openDelete(d: DocumentInfo) {
  deleteTarget.value = d
  genCaptcha()
}

async function confirmDelete() {
  if (!deleteTarget.value) return
  if (captchaInput.value !== captchaCode.value) {
    ElMessage.error('验证码错误，请重新输入')
    genCaptcha()
    return
  }
  try {
    await documentApi.delete(deleteTarget.value.id)
    ElMessage.success('文件已删除')
    deleteTarget.value = null
    await load()
  } catch (e) {
    ElMessage.error(explainApiError(e))
    deleteTarget.value = null
  }
}

/** 判定我能否编辑（体验层，真正拦截在后端） */
const canEdit = computed(() => {
  const m = auth.membershipOf(projectId.value)
  return !!m && m.actions.includes('EDIT')
})

async function load() {
  loading.value = true
  error.value = null
  try {
    docs.value = await documentApi.list(projectId.value, {
      with_versions: true,
      stage: stage.value || undefined,
    })
  } catch (e) {
    error.value = explainApiError(e)
  } finally {
    loading.value = false
  }
}

onMounted(async () => {
  await load()
  try {
    docTypes.value = await dictApi.items('DOC_TYPE')
  } catch {
    docTypes.value = []
  }
})

// 阶段切换（左上角下拉）时，路由 query 变了但组件不重新挂载，需手动重载文档列表
watch(stage, () => load())

/** 当前有效版本 */
function currentVersion(d: DocumentInfo): DocumentVersionInfo | undefined {
  return d.versions.find((v) => v.id === d.current_version_id)
}

/** 最新版本（不管状态） */
function latestVersion(d: DocumentInfo): DocumentVersionInfo | undefined {
  return d.versions[d.versions.length - 1]
}

/** 是否有审批中的版本 —— 用于禁用上传 */
function hasInflight(d: DocumentInfo): boolean {
  return d.versions.some((v) => ['CHECKING', 'REVIEWING', 'APPROVED'].includes(v.state))
}

async function openDetail(d: DocumentInfo) {
  detailDoc.value = d
  detailOpen.value = true
  // 默认展示当前有效版本的审批轨迹
  const v = currentVersion(d) || latestVersion(d)
  if (v) await loadTrace(v.id)
}

async function loadTrace(versionId: string) {
  traceVersionId.value = versionId
  traceLoading.value = true
  try {
    trace.value = await documentApi.trace(versionId)
  } catch {
    trace.value = null
  } finally {
    traceLoading.value = false
  }
}

async function refreshDetail() {
  if (!detailDoc.value) return
  const fresh = await documentApi.detail(detailDoc.value.id)
  detailDoc.value = fresh
  const idx = docs.value.findIndex((x) => x.id === fresh.id)
  if (idx >= 0) docs.value[idx] = fresh
  if (traceVersionId.value) await loadTrace(traceVersionId.value)
}

/** ---------------- 新建文档 ---------------- */

async function openCreate() {
  createForm.title = ''
  createForm.titleSelect = ''
  createForm.doc_code = null
  createForm.doc_no = ''
  createForm.category_id = null
  createForm.discipline = '结构'
  createForm.secret_level = 'INTERNAL'
  createFile.value = null
  // 加载本阶段标准清单，供「文件名称」下拉选择
  if (stage.value) {
    try {
      catalogOptions.value = await checklistApi.list(projectId.value, stage.value)
    } catch {
      catalogOptions.value = []
    }
  } else {
    catalogOptions.value = []
  }
  createOpen.value = true
}

async function doCreate() {
  if (!createForm.title.trim()) {
    ElMessage.warning('请填写文件名称')
    return
  }
  try {
    const doc = await documentApi.create({
      project_id: projectId.value,
      stage_code: (stage.value as StageCode) || 'DESIGN',
      title: createForm.title,
      doc_no: createForm.doc_no || null,
      doc_code: createForm.doc_code,
      category_id: createForm.category_id,
      discipline: createForm.discipline,
      secret_level: createForm.secret_level,
    })
    // 选了文件 → 直接上传第一个版本（草稿）
    if (createFile.value) {
      await documentApi.uploadVersion(doc.id, createFile.value)
    }
    ElMessage.success(createFile.value ? '文件已创建并上传（草稿）' : '文件已创建，接下来上传第一个版本')
    createOpen.value = false
    createFile.value = null
    await load()
  } catch (e) {
    ElMessage.error(explainApiError(e))
  }
}

/** ---------------- 上传版本 ---------------- */

function openUpload(d: DocumentInfo) {
  if (hasInflight(d)) {
    ElMessage.warning('该文件已有版本在审批中，不允许同时存在两个审批中的版本')
    return
  }
  uploadTarget.value = d
  uploadFile.value = null
  uploadSummary.value = ''
  uploadOpen.value = true
}

function onFileChange(f: UploadFile) {
  uploadFile.value = (f.raw as File) ?? null
}

async function doUpload() {
  if (!uploadTarget.value || !uploadFile.value) {
    ElMessage.warning('请选择文件')
    return
  }
  try {
    const v = await documentApi.uploadVersion(uploadTarget.value.id, uploadFile.value, {
      change_summary: uploadSummary.value || undefined,
    })
    ElMessage.success(`已上传 ${v.version_no}（草稿），可提交校审`)
    uploadOpen.value = false
    await load()
  } catch (e) {
    ElMessage.error(explainApiError(e))
  }
}

/** ---------------- 状态机操作 ---------------- */

async function doSubmit(v: DocumentVersionInfo) {
  try {
    await ElMessageBox.confirm(
      `提交 ${v.version_no} 进入三级校审：\n校核 → 审核 → 批准 → 发布\n\n` +
        `注意：校核 / 审核 / 批准必须由不同人员完成。`,
      '提交校审',
      { confirmButtonText: '确认提交', cancelButtonText: '取消' },
    )
  } catch {
    return
  }
  try {
    await documentApi.submit(v.id)
    ElMessage.success('已提交校审')
    await refreshDetail()
    await load()
  } catch (e) {
    ElMessage.error(explainApiError(e))
  }
}

async function doDecide(v: DocumentVersionInfo, action: 'APPROVE' | 'RETURN') {
  try {
    const { value: comment } = await ElMessageBox.prompt(
      action === 'APPROVE'
        ? `通过 ${v.version_no} 当前审批节点。`
        : `退回 ${v.version_no}。退回后文件将回到草稿状态，你可以填写修改要求。`,
      action === 'APPROVE' ? '审批通过' : '退回修改',
      {
        confirmButtonText: action === 'APPROVE' ? '确认通过' : '确认退回',
        cancelButtonText: '取消',
        inputPlaceholder: '审批意见（建议填写，会保留在审批轨迹里）',
      },
    )
    await documentApi.decide(v.id, action, comment || undefined)
    ElMessage.success(action === 'APPROVE' ? '已通过' : '已退回')
    await refreshDetail()
    await load()
  } catch (e) {
    if (e !== 'cancel' && e !== 'close') ElMessage.error(explainApiError(e))
  }
}

async function doPublish(v: DocumentVersionInfo) {
  try {
    await ElMessageBox.confirm(
      `发布 ${v.version_no}？\n\n` +
        `发布后该版本成为本文件的唯一有效版本，此前的有效版本会自动作废（记录保留）。\n` +
        `已发布版本不可回退，如需修改必须发起修订生成新版本。`,
      '发布文件',
      { confirmButtonText: '确认发布', cancelButtonText: '取消', type: 'warning' },
    )
  } catch {
    return
  }
  try {
    const r = await documentApi.publish(v.id)
    // 后端 message 会回带"来源参数需重新核验"，必须透传，不能吞掉
    ElMessage.success(r.message || '发布成功')
    if (r.message && r.message.includes('重新核验')) {
      ElMessage.warning('请到「设计输入管理」重新核验受影响的参数')
      await checkStale()
    }
    await refreshDetail()
    await load()
  } catch (e) {
    ElMessage.error(explainApiError(e))
  }
}

async function doRevision(d: DocumentInfo) {
  try {
    const { value: reason } = await ElMessageBox.prompt(
      `基于当前有效版本发起修订。\n\n` +
        `已发布版本不可直接修改 —— 这是为了保证"发出去的图纸不会被悄悄改掉"。\n` +
        `修订期间原版本仍是有效版本，不会出现"没有有效版本可用"的空窗。`,
      '发起修订',
      {
        confirmButtonText: '发起修订',
        cancelButtonText: '取消',
        inputPlaceholder: '修订原因（必填，例如：根据详勘 V2 参数调整桩长）',
        inputValidator: (v) => (v && v.trim().length >= 4 ? true : '请填写不少于 4 个字的修订原因'),
      },
    )
    await documentApi.startRevision(d.id, reason)
    ElMessage.success('已生成修订版本，请上传新文件')
    await refreshDetail()
    await load()
  } catch (e) {
    if (e !== 'cancel' && e !== 'close') ElMessage.error(explainApiError(e))
  }
}

async function doVoid(v: DocumentVersionInfo, doc: DocumentInfo) {
  try {
    const { value: reason } = await ElMessageBox.prompt(
      `作废 ${v.version_no}。\n\n作废必须填写原因，且版本记录不会被物理删除（保留完整历史）。`,
      '作废版本',
      {
        confirmButtonText: '确认作废',
        cancelButtonText: '取消',
        inputPlaceholder: '作废原因（必填）',
        inputValidator: (x) => (x && x.trim().length >= 4 ? true : '请填写不少于 4 个字的原因'),
      },
    )
    await documentApi.void(v.id, reason)
    ElMessage.warning('已作废')
    await refreshDetail()
    await load()
    void doc
  } catch (e) {
    if (e !== 'cancel' && e !== 'close') ElMessage.error(explainApiError(e))
  }
}

/** ---------------- 下载 / 预览 ---------------- */

/**
 * 打开文件。默认走**内嵌预览**（后端对 PDF/图片/文本返回 inline），
 * 浏览器直接显示内容；需要落盘时再加 ?download=1 强制另存为。
 *
 * 之前一律 attachment + window.open，结果新标签页是空的、文件悄悄进了下载目录，
 * 用户以为"下载完看不了文件"。
 */
async function doDownload(v: DocumentVersionInfo, saveAs = false) {
  try {
    const tok = await documentApi.downloadToken(v.id)
    const url = saveAs ? `${tok.url}${tok.url.includes('?') ? '&' : '?'}download=1` : tok.url
    window.open(url, '_blank')
    ElMessage.info(saveAs ? '已开始下载（链接 5 分钟内有效）' : '已在新标签页打开（链接 5 分钟内有效）')
  } catch (e) {
    ElMessage.error(explainApiError(e))
  }
}

/** ---------------- STALE 提示 ---------------- */

const staleTip = ref<number | null>(null)

async function checkStale() {
  try {
    const r = await designInputApi.refreshStale(projectId.value)
    staleTip.value = r.stale_count
  } catch {
    staleTip.value = null
  }
}

onMounted(checkStale)

/** 版本状态标签 */
const stateTag = (s: string) => DOCUMENT_STATE_TAG[s as keyof typeof DOCUMENT_STATE_TAG] ?? 'info'
</script>

<template>
  <div class="page">
    <StageContextBar :project-id="projectId" :stage="stage" active="documents" />
    <!-- 顶部 -->
    <div class="head app-card">
      <div>
        <div class="sec-title" style="margin-bottom: 10px">
          文件与版本管理
          <span class="more" @click="$router.push({ name: 'project-detail', params: { id: projectId } })">
            返回项目总览
          </span>
        </div>
        <p class="t-grey t-sm" style="margin: 0">
          版本状态机：草稿 → 校核中 → 审核中 → 已批准 → 已发布 → 已作废。
          <b class="t-amber">未发布版本不可被下游引用。</b>
        </p>
      </div>
      <div class="head-actions">
        <el-button v-if="canEdit" type="primary" @click="openCreate">新建文件</el-button>
      </div>
    </div>

    <el-alert
      v-if="staleTip"
      type="error"
      show-icon
      :closable="false"
      style="margin-top: 14px"
      :title="`有 ${staleTip} 项设计输入参数的来源已失效`"
    >
      <template #default>
        <div style="font-size: 12.5px">
          来源文件发布了新版本，需要到「设计输入管理」重新核验。
          <el-button link type="primary" size="small" @click="$router.push({ name: 'design-inputs', params: { id: projectId }, query: { stage: 'DESIGN' } })">
            去处理
          </el-button>
        </div>
      </template>
    </el-alert>

    <el-skeleton v-if="loading" :rows="8" animated style="margin-top: 16px" />
    <el-alert v-else-if="error" :title="error" type="error" show-icon :closable="false" />

    <!-- 文件表 -->
    <div v-else class="app-card" style="margin-top: 16px; overflow: hidden">
      <el-table :data="docs" style="width: 100%" :empty-text="'暂无文件，点击右上角「新建文件」开始'">
        <el-table-column label="文件" min-width="260">
          <template #default="{ row }">
            <a class="doc-title" @click="openDetail(row)">{{ row.title }}</a>
            <div class="doc-meta t-grey t-sm">
              <span class="t-mono">{{ row.doc_no || '无编号' }}</span>
              · {{ row.discipline }}
              <el-tag size="small" effect="plain" class="ml4">
                {{ row.category_name || '未分类' }}
              </el-tag>
              <el-tag
                v-if="row.secret_level !== 'INTERNAL'"
                size="small"
                type="warning"
                effect="plain"
                class="ml4"
              >
                {{ SECRET_LEVEL_LABEL[row.secret_level] || row.secret_level }}
              </el-tag>
            </div>
          </template>
        </el-table-column>

        <el-table-column label="阶段" width="96">
          <template #default="{ row }">
            <span class="t-sm">{{ STAGE_LABEL[row.stage_code as keyof typeof STAGE_LABEL] || row.stage_code }}</span>
          </template>
        </el-table-column>

        <el-table-column label="当前有效版本" width="150">
          <template #default="{ row }">
            <template v-if="currentVersion(row)">
              <b class="t-teal">{{ currentVersion(row)!.version_no }}</b>
              <div class="t-grey t-sm">已发布</div>
            </template>
            <el-tooltip v-else content="该文件还没有已发布版本，下游不可引用" placement="top">
              <span class="t-amber t-sm">尚无有效版本</span>
            </el-tooltip>
          </template>
        </el-table-column>

        <el-table-column label="最新版本" width="140">
          <template #default="{ row }">
            <template v-if="latestVersion(row)">
              <el-tag :type="stateTag(latestVersion(row)!.state)" size="small" effect="light">
                {{ latestVersion(row)!.version_no }} ·
                {{ DOCUMENT_STATE_LABEL[latestVersion(row)!.state] }}
              </el-tag>
              <div v-if="latestVersion(row)!.is_self_checked" class="t-amber t-sm">
                自校
              </div>
            </template>
            <span v-else class="t-grey t-sm">—</span>
          </template>
        </el-table-column>

        <el-table-column label="版本数" width="76" align="center">
          <template #default="{ row }">{{ row.version_count }}</template>
        </el-table-column>

        <el-table-column label="操作" width="210" align="right">
          <template #default="{ row }">
            <el-button link type="primary" size="small" @click="openDetail(row)">版本</el-button>
            <el-button
              v-if="canEdit && !hasInflight(row)"
              link
              size="small"
              @click="openUpload(row)"
            >
              上传新版本
            </el-button>
            <el-button
              v-else-if="canEdit && hasInflight(row)"
              link
              size="small"
              disabled
            >
              审批中
            </el-button>
            <el-button
              v-if="canEdit && currentVersion(row)"
              link
              size="small"
              @click="doRevision(row)"
            >
              修订
            </el-button>
            <el-button v-if="canEdit" link size="small" type="danger" @click="openDelete(row)">
              删除
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <StageChecklist :project-id="projectId" :stage="stage" @changed="load" />

    <!-- 规则说明 -->
    <div class="rules">
      <b>版本状态机的四条铁律（后端强制校验，前端只是提示）：</b>
      <ol>
        <li><b>未发布版本不可被下游引用</b> —— 施工、变更、成果交付都只能引用「已发布」版本。</li>
        <li><b>同一文件不允许同时存在两个审批中的版本</b> —— 防止版本分叉。</li>
        <li><b>已发布版本不可回退</b> —— 要改就发起修订生成新版本，保证"发出去的图纸不会被悄悄改掉"。</li>
        <li><b>同一时刻最多一个已发布版本；作废必须填原因且不物理删除</b> —— 完整历史可追溯。</li>
      </ol>
    </div>

    <!-- ============ 版本详情抽屉 ============ -->
    <el-drawer v-model="detailOpen" size="640px" :title="detailDoc?.title || '文件版本'">
      <template v-if="detailDoc">
        <el-descriptions :column="2" border size="small">
          <el-descriptions-item label="文件编号">
            <span class="t-mono">{{ detailDoc.doc_no || '—' }}</span>
          </el-descriptions-item>
          <el-descriptions-item label="专业">{{ detailDoc.discipline }}</el-descriptions-item>
          <el-descriptions-item label="所属阶段">
            {{ detailDoc.stage_label || detailDoc.stage_code }}
          </el-descriptions-item>
          <el-descriptions-item label="敏感等级">
            {{ SECRET_LEVEL_LABEL[detailDoc.secret_level] || detailDoc.secret_level }}
          </el-descriptions-item>
        </el-descriptions>

        <div class="sec-title" style="margin-top: 20px">版本列表（{{ detailDoc.versions.length }}）</div>

        <div
          v-for="v in [...detailDoc.versions].reverse()"
          :key="v.id"
          class="vcard"
          :class="{
            current: v.id === detailDoc.current_version_id,
            active: v.id === traceVersionId,
          }"
          @click="loadTrace(v.id)"
        >
          <div class="vc-head">
            <div class="vc-l">
              <b class="vc-no">{{ v.version_no }}</b>
              <el-tag :type="stateTag(v.state)" size="small" effect="light">
                {{ DOCUMENT_STATE_LABEL[v.state] }}
              </el-tag>
              <el-tag v-if="v.id === detailDoc.current_version_id" type="success" size="small" effect="dark">
                当前有效
              </el-tag>
              <el-tag v-if="v.is_self_checked" type="warning" size="small" effect="plain">
                自校
              </el-tag>
            </div>
            <div class="vc-r t-grey t-sm">
              {{ v.created_by_name || '—' }} · {{ formatDate(v.created_at) }}
            </div>
          </div>

          <div v-if="v.change_summary" class="vc-summary">{{ v.change_summary }}</div>

          <div v-if="v.is_self_checked" class="vc-selfcheck">
            本版本有节点由同一人处理（人员不足，走自校流程）：{{ v.self_check_reason }}
          </div>

          <div v-if="v.void_reason" class="vc-void">作废原因：{{ v.void_reason }}</div>

          <div v-if="v.file" class="vc-file t-grey t-sm">
            {{ v.file.original_name }}
            <span v-if="v.file.size">（{{ (v.file.size / 1024).toFixed(1) }} KB）</span>
          </div>

          <!-- 操作按钮完全由后端下发的 available_actions 驱动 -->
          <div class="vc-actions" @click.stop>
            <el-button
              v-if="v.available_actions.includes('download')"
              size="small"
              type="primary"
              plain
              @click="doDownload(v)"
            >
              查看
            </el-button>
            <el-button
              v-if="v.available_actions.includes('download')"
              size="small"
              @click="doDownload(v, true)"
            >
              下载
            </el-button>
            <el-button
              v-if="v.available_actions.includes('submit')"
              size="small"
              type="primary"
              @click="doSubmit(v)"
            >
              提交校审
            </el-button>
            <el-button
              v-if="v.available_actions.includes('approve')"
              size="small"
              type="success"
              @click="doDecide(v, 'APPROVE')"
            >
              通过
            </el-button>
            <el-button
              v-if="v.available_actions.includes('return')"
              size="small"
              type="warning"
              @click="doDecide(v, 'RETURN')"
            >
              退回
            </el-button>
            <el-button
              v-if="v.available_actions.includes('publish')"
              size="small"
              type="primary"
              @click="doPublish(v)"
            >
              发布
            </el-button>
            <el-button
              v-if="v.available_actions.includes('revise')"
              size="small"
              @click="detailDoc && doRevision(detailDoc)"
            >
              发起修订
            </el-button>
            <el-button
              v-if="v.available_actions.includes('void')"
              size="small"
              type="danger"
              plain
              @click="detailDoc && doVoid(v, detailDoc)"
            >
              作废
            </el-button>
          </div>
        </div>

        <!-- 审批轨迹 -->
        <div class="sec-title" style="margin-top: 22px">
          审批轨迹
          <span class="more" style="cursor: default">
            {{ traceVersionId ? '点击上方版本可切换' : '选择版本查看' }}
          </span>
        </div>

        <el-skeleton v-if="traceLoading" :rows="3" animated />
        <div v-else-if="!trace" class="t-grey t-sm">该版本尚未提交审批。</div>
        <div v-else>
          <div class="trace-head">
            流程状态：
            <el-tag size="small" :type="trace.status === 'FINISHED' ? 'success' : 'primary'" effect="light">
              {{ trace.status === 'FINISHED' ? '已结束' : '进行中' }}
            </el-tag>
            <span v-if="trace.current_node" class="ml8">
              当前节点：<b>{{ NODE_LABEL[trace.current_node] || trace.current_node }}</b>
            </span>
            <span class="ml8 t-grey">
              第 {{ trace.round }} 轮
              <template v-if="trace.initiator"> · 发起人 {{ trace.initiator }}</template>
            </span>
          </div>

          <el-timeline style="margin-top: 12px; padding-left: 4px">
            <el-timeline-item
              v-for="t in trace.tasks"
              :key="t.id"
              :type="t.action === 'APPROVE' ? 'success' : t.action ? 'warning' : 'primary'"
              :hollow="!t.action"
              size="normal"
            >
              <div class="tk">
                <div class="tk-head">
                  <b>{{ NODE_LABEL[t.node_code] || t.node_code }}</b>
                  <el-tag v-if="t.is_self_check" size="small" type="warning" effect="plain">自校</el-tag>
                  <span class="t-grey t-sm">
                    {{ t.assignee_name || '未指派' }}
                    <template v-if="t.assignee_role">（{{ t.assignee_role }}）</template>
                  </span>
                  <span class="tk-action">
                    <el-tag
                      v-if="t.action"
                      size="small"
                      :type="t.action === 'APPROVE' ? 'success' : 'warning'"
                      effect="light"
                    >
                      {{ TASK_ACTION_LABEL[t.action] }}
                    </el-tag>
                    <el-tag v-else size="small" effect="plain">待处理</el-tag>
                  </span>
                </div>
                <div v-if="t.comment" class="tk-comment">{{ t.comment }}</div>
                <div class="t-grey t-sm">
                  <template v-if="t.acted_at">处理于 {{ formatDateTime(t.acted_at) }}</template>
                  <template v-else-if="t.due_at">截止 {{ formatDateTime(t.due_at) }}</template>
                  <template v-else>第 {{ t.round }} 轮</template>
                </div>
              </div>
            </el-timeline-item>
          </el-timeline>

          <div class="trace-note">
            历轮退回的记录会<b>全部保留</b> —— 可以回答"这份图纸被退回过几次、每次是谁提了什么意见"。
          </div>
        </div>
      </template>
    </el-drawer>

    <!-- ============ 新建文件 ============ -->
    <el-dialog v-model="createOpen" title="新建文件" width="520px">
      <el-form label-width="88px" label-position="right">
        <el-form-item label="文件名称" required>
          <el-select
            v-model="createForm.titleSelect"
            placeholder="选择本阶段需上传的文件"
            clearable
            style="width: 100%"
            @change="onTitleSelect"
          >
            <el-option
              v-for="it in catalogOptions"
              :key="it.doc_code"
              :label="`${it.doc_code} · ${it.doc_name}`"
              :value="it.doc_code"
            />
            <el-option label="其他（自定义名称）" value="OTHER" />
          </el-select>
        </el-form-item>
        <el-form-item v-if="createForm.titleSelect === 'OTHER'" label="自定义名称" required>
          <el-input v-model="createForm.title" placeholder="请输入文件名称" />
        </el-form-item>
        <el-form-item label="文件编号">
          <el-input v-model="createForm.doc_no" placeholder="例如：JG-01" />
        </el-form-item>
        <el-form-item label="文件类型">
          <el-select v-model="createForm.category_id" placeholder="选择类型" clearable style="width: 100%">
            <el-option v-for="t in docTypes" :key="t.id" :label="t.name" :value="t.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="专业">
          <el-input v-model="createForm.discipline" />
        </el-form-item>
        <el-form-item label="敏感等级">
          <el-select v-model="createForm.secret_level" style="width: 100%">
            <el-option label="公开" value="PUBLIC" />
            <el-option label="内部" value="INTERNAL" />
            <el-option label="受限（需单独授权）" value="RESTRICTED" />
            <el-option label="保密（需授权+下载留痕）" value="SECRET" />
          </el-select>
        </el-form-item>
        <el-form-item label="上传文件">
          <el-upload
            :auto-upload="false"
            :limit="1"
            :on-change="onCreateFileChange"
            :on-remove="() => (createFile = null)"
            drag
            style="width: 100%"
          >
            <div class="up-hint">将文件拖到此处，或<em>点击选择</em>（可选）</div>
          </el-upload>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="createOpen = false">取消</el-button>
        <el-button type="primary" @click="doCreate">创建</el-button>
      </template>
    </el-dialog>

    <!-- ============ 上传版本 ============ -->
    <el-dialog v-model="uploadOpen" :title="`上传新版本 · ${uploadTarget?.title || ''}`" width="520px">
      <el-alert
        type="info"
        :closable="false"
        show-icon
        style="margin-bottom: 14px"
        title="上传后版本状态为「草稿」，需提交校审 → 校核 → 审核 → 批准 → 发布后才可被下游引用"
      />
      <el-form label-width="88px">
        <el-form-item label="文件" required>
          <el-upload
            :auto-upload="false"
            :limit="1"
            :on-change="onFileChange"
            :on-remove="() => (uploadFile = null)"
            drag
            style="width: 100%"
          >
            <div class="up-hint">将文件拖到此处，或<em>点击选择</em></div>
            <template #tip>
              <div class="t-grey t-sm" style="margin-top: 6px">
                支持 pdf / dwg / docx / xlsx 等设计文件。相同内容会自动去重，不重复占用存储。
              </div>
            </template>
          </el-upload>
        </el-form-item>
        <el-form-item label="变更说明">
          <el-input
            v-model="uploadSummary"
            type="textarea"
            :rows="3"
            placeholder="本版相对上一版改了什么（建议填写，便于追溯）"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="uploadOpen = false">取消</el-button>
        <el-button type="primary" @click="doUpload">上传</el-button>
      </template>
    </el-dialog>

    <!-- ============ 删除文件（验证码确认）============ -->
    <el-dialog v-model="deleteOpen" title="删除文件" width="430px">
      <div v-if="deleteTarget">
        <p style="margin-bottom: 12px">
          确定删除文件「<b>{{ deleteTarget.title }}</b>」吗？
          将删除此文件及其所有版本，<b class="t-red">不可恢复</b>。
        </p>
        <p class="t-grey t-sm" style="margin-bottom: 10px">请输入下方图形中的数字验证码以确认删除：</p>
        <div class="captcha-row">
          <canvas
            ref="captchaCanvas"
            width="140"
            height="48"
            class="captcha-canvas"
            title="点击刷新验证码"
            @click="genCaptcha"
          />
          <el-input
            v-model="captchaInput"
            placeholder="输入 4 位数字"
            maxlength="4"
            style="width: 150px"
            @keyup.enter="confirmDelete"
          />
        </div>
      </div>
      <template #footer>
        <el-button @click="deleteOpen = false">取消</el-button>
        <el-button type="danger" @click="confirmDelete">确认删除</el-button>
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

.doc-title {
  font-weight: 600;
  color: var(--blue);
  cursor: pointer;
}
.doc-title:hover {
  text-decoration: underline;
}
.doc-meta {
  margin-top: 3px;
}
.ml4 {
  margin-left: 4px;
}
.ml8 {
  margin-left: 8px;
}

/* ---------------- 版本卡片 ---------------- */
.vcard {
  border: 1px solid var(--line);
  border-radius: 6px;
  padding: 11px 14px;
  margin-bottom: 10px;
  cursor: pointer;
  transition: all 0.15s;
  background: #fff;
}
.vcard:hover {
  border-color: var(--blue);
}
.vcard.active {
  border-color: var(--blue);
  box-shadow: 0 0 0 2px var(--blue-soft);
}
.vcard.current {
  background: #f6fcfb;
}

.vc-head {
  display: flex;
  align-items: center;
  gap: 8px;
}
.vc-l {
  display: flex;
  align-items: center;
  gap: 7px;
}
.vc-no {
  font-size: 14px;
}
.vc-r {
  margin-left: auto;
}
.vc-summary {
  margin-top: 7px;
  font-size: 12.5px;
  color: var(--ink-2);
  line-height: 1.6;
}
.vc-selfcheck {
  margin-top: 7px;
  font-size: 12px;
  background: var(--amber-soft);
  border: 1px solid #f0dcb0;
  color: #7a5a17;
  border-radius: 4px;
  padding: 6px 10px;
  line-height: 1.6;
}
.vc-void {
  margin-top: 7px;
  font-size: 12px;
  color: var(--red);
}
.vc-file {
  margin-top: 6px;
}
.vc-actions {
  margin-top: 10px;
  display: flex;
  gap: 7px;
  flex-wrap: wrap;
}

/* ---------------- 审批轨迹 ---------------- */
.trace-head {
  font-size: 13px;
  color: var(--ink-2);
  padding: 8px 0;
  border-bottom: 1px dashed var(--line);
}
.tk-head {
  display: flex;
  align-items: center;
  gap: 7px;
  flex-wrap: wrap;
}
.tk-action {
  margin-left: auto;
}
.tk-comment {
  margin: 4px 0;
  font-size: 12.5px;
  color: var(--ink-2);
  background: #f7f9fc;
  border-radius: 4px;
  padding: 6px 10px;
  line-height: 1.6;
}
.trace-note {
  margin-top: 8px;
  font-size: 12px;
  color: var(--grey);
  background: #f7f9fc;
  border-radius: 4px;
  padding: 8px 11px;
  line-height: 1.7;
}

/* ---------------- 规则说明 ---------------- */
.rules {
  margin-top: 16px;
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

.up-hint {
  font-size: 13px;
  color: var(--grey);
  padding: 18px 0;
}
.up-hint em {
  color: var(--blue);
  font-style: normal;
}

.captcha-row {
  display: flex;
  align-items: center;
  gap: 12px;
}
.captcha-canvas {
  border: 1px solid var(--line, #e3e8f0);
  border-radius: 6px;
  cursor: pointer;
  background: #eef2f7;
}
</style>
