<script setup lang="ts">
/**
 * 设计输入管理 —— 参数溯源链的界面。
 *
 * 这张表是整个设计阶段最有辨识度的东西：
 *   每个参数都能看到它来自哪份勘察报告的哪个版本、第几页哪张表，
 *   并且能一眼看出**来源文件是否已有更新版本**（需要重新核验）。
 *
 * 锁定语义也在这里体现：
 *   必填参数全部核验 → 可锁定；锁定后修改必须走设计变更。
 */
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'

import { designInputApi, documentApi, ledgerApi } from '@/api'
import { explainApiError } from '@/api/http'
import type { DesignInputSummary, DesignParam, LedgerItem } from '@/api/types'
import {
  DOCUMENT_STATE_LABEL,
  STAGE_LABEL,
  VERIFY_STATUS_LABEL,
  VERIFY_STATUS_TAG,
  VerifyStatus,
} from '@/api/types'
import { useAuthStore } from '@/stores/auth'
import { formatDateTime } from '@/utils/format'

const route = useRoute()
const auth = useAuthStore()

const projectId = computed(() => route.params.id as string)

/**
 * 一级切换。
 *
 * 新方向下平台主体是**文档管理**，所以默认落在「输入文件库」——
 * 设计人员最常见的行为是"查阅上游给了什么资料"。
 * 「参数溯源」是原有能力，保留在第二个标签页，不丢功能。
 */
const tab = ref<'library' | 'params'>('library')

/* ---------------- 输入文件库 ---------------- */

const libLoading = ref(false)
const libError = ref<string | null>(null)
const libDocs = ref<LedgerItem[]>([])

/** 只列上游阶段（设计之前的阶段）：这些才是"设计输入" */
const UPSTREAM_STAGES = ['PRE_SURVEY', 'INVESTIGATION', 'DESIGN_TEST_PILE']

async function loadLibrary() {
  libLoading.value = true
  libError.value = null
  try {
    // 取项目台账（后端按我的单位责任与密级过滤），再筛出上游阶段
    const led = await ledgerApi.list(projectId.value)
    libDocs.value = (led.items || []).filter((i) =>
      UPSTREAM_STAGES.includes(String(i.stage_code)),
    )
  } catch (e) {
    libError.value = explainApiError(e)
  } finally {
    libLoading.value = false
  }
}

const libPublished = computed(
  () => libDocs.value.filter((d) => d.effective_state === 'PUBLISHED').length,
)
const libInflight = computed(() => libDocs.value.filter((d) => d.pending_count > 0).length)

/** 下载：走短时效签名 URL */
async function downloadDoc(row: LedgerItem) {
  if (!row.current_version_no) {
    ElMessage.warning('该文件尚未发布，没有可下载的版本')
    return
  }
  try {
    // 台账只给了版本号，要拿 version_id 才能取下载令牌
    const detail = await documentApi.versions(row.document_id)
    const cur = (detail || []).find((v) => v.version_no === row.current_version_no)
    if (!cur) {
      ElMessage.warning('未找到当前有效版本')
      return
    }
    const tok = await documentApi.downloadToken(cur.id)
    window.open(tok.url, '_blank')
    ElMessage.info('下载链接 5 分钟内有效')
  } catch (e) {
    ElMessage.error(explainApiError(e))
  }
}

function onTabChange(name: string | number) {
  if (name === 'library' && !libDocs.value.length) loadLibrary()
  if (name === 'params' && !params.value.length) load()
}

/* ---------------- 参数溯源 ---------------- */

const loading = ref(false)
const error = ref<string | null>(null)
const params = ref<DesignParam[]>([])
const summary = ref<DesignInputSummary | null>(null)

/** 核验中的参数 id（按钮 loading） */
const acting = ref<string | null>(null)

/** 分组顺序：与《设计阶段-落地版》的三层结构一致 */
const GROUP_ORDER = ['场地与地层', '荷载与上部结构', '边界与约束']

const grouped = computed(() => {
  const map = new Map<string, DesignParam[]>()
  for (const p of params.value) {
    const g = p.param_group || '其他'
    if (!map.has(g)) map.set(g, [])
    map.get(g)!.push(p)
  }
  return GROUP_ORDER.filter((g) => map.has(g))
    .concat([...map.keys()].filter((g) => !GROUP_ORDER.includes(g)))
    .map((g) => ({ name: g, items: map.get(g)! }))
})

/** 我是否有编辑权限（决定是否显示核验按钮）。
    设计输入属于设计阶段，所以按"我在设计阶段是不是主办单位"判断。 */
const canEdit = computed(() => auth.can(projectId.value, 'EDIT', 'DESIGN' as never))

const hasStale = computed(() => (summary.value?.stale ?? 0) > 0)

async function load() {
  loading.value = true
  error.value = null
  try {
    const [s, list] = await Promise.all([
      designInputApi.summary(projectId.value),
      designInputApi.list(projectId.value),
    ])
    summary.value = s
    params.value = list
  } catch (e) {
    error.value = explainApiError(e)
  } finally {
    loading.value = false
  }
}

// 默认展示「输入文件库」，所以进来先加载它；参数溯源在切页时按需加载
onMounted(loadLibrary)

/** ---------------- 核验动作 ---------------- */

async function doVerify(p: DesignParam, action: string) {
  acting.value = p.id
  const wasStale = p.verify_status === VerifyStatus.STALE
  try {
    await designInputApi.verify(projectId.value, p.id, { action })
    ElMessage.success(
      wasStale ? `「${p.param_name}」已按新版本重新核验通过` : `「${p.param_name}」核验通过`,
    )
    await load()
  } catch (e) {
    ElMessage.error(explainApiError(e))
  } finally {
    acting.value = null
  }
}

async function doModify(p: DesignParam) {
  try {
    const { value: form } = await ElMessageBox.prompt(
      `当前值：${p.display_value}\n请填写修改后的取值（数值或文本），并在下方说明修改依据。`,
      `修改「${p.param_name}」取值`,
      {
        confirmButtonText: '提交',
        cancelButtonText: '取消',
        inputPlaceholder: '新的取值',
        inputValidator: (v) => (v && v.trim() ? true : '取值不能为空'),
        // 需要额外的理由输入，用 message 提示 + 二次确认
      },
    )
    // 依据是必填的 —— 溯源链不能断
    const { value: note } = await ElMessageBox.prompt(
      '请说明修改依据（谁改的、按什么依据改）。原来源信息会保留，修改记录会留痕。',
      '修改依据（必填）',
      {
        confirmButtonText: '确认修改',
        cancelButtonText: '取消',
        inputPlaceholder: '例如：经勘察单位复函确认，③层 fak 调整为 300kPa',
        inputValidator: (v) => (v && v.trim().length >= 4 ? true : '请填写不少于 4 个字的依据'),
      },
    )

    const num = Number(form)
    await designInputApi.verify(projectId.value, p.id, {
      action: 'modify',
      new_value_num: Number.isFinite(num) && form.trim() !== '' ? num : undefined,
      new_value_text: Number.isFinite(num) && form.trim() !== '' ? undefined : form,
      note,
    })
    ElMessage.success('已修改并留痕')
    await load()
  } catch (e) {
    if (e !== 'cancel' && e !== 'close') ElMessage.error(explainApiError(e))
  }
}

async function doDoubtful(p: DesignParam) {
  try {
    const { value: note } = await ElMessageBox.prompt(
      '标记存疑后该参数会挂起，需要资料提供方澄清。请说明存疑原因与需要谁澄清什么。',
      `标记「${p.param_name}」为存疑`,
      {
        confirmButtonText: '标记存疑',
        cancelButtonText: '取消',
        inputPlaceholder: '例如：与相邻同类项目实测值偏差 14%，需勘察单位补充原状土复验',
        inputValidator: (v) => (v && v.trim().length >= 4 ? true : '请填写不少于 4 个字的说明'),
      },
    )
    await designInputApi.verify(projectId.value, p.id, { action: 'doubtful', note })
    ElMessage.warning('已标记存疑')
    await load()
  } catch (e) {
    if (e !== 'cancel' && e !== 'close') ElMessage.error(explainApiError(e))
  }
}

/** ---------------- 锁定 / 解锁 ---------------- */

async function doLock() {
  const s = summary.value
  if (!s) return
  try {
    await ElMessageBox.confirm(
      `即将锁定 ${s.total} 项设计输入。\n\n` +
        `锁定后任何参数修改都必须走设计变更流程 —— 这是为了保证设计依据不被悄悄改掉。\n\n` +
        `确认锁定？`,
      '锁定设计输入',
      { confirmButtonText: '确认锁定', cancelButtonText: '再检查一下', type: 'warning' },
    )
  } catch {
    return
  }
  try {
    const r = await designInputApi.lock(projectId.value)
    ElMessage.success(`已锁定 ${r.locked_count} 项设计输入`)
    await load()
  } catch (e) {
    ElMessage.error(explainApiError(e))
  }
}

async function doUnlock() {
  try {
    const { value: reason } = await ElMessageBox.prompt(
      '解锁是特权操作，正常流程应走设计变更。请填写原因（建议关联变更单号）。',
      '解锁设计输入',
      {
        confirmButtonText: '确认解锁',
        cancelButtonText: '取消',
        inputPlaceholder: '例如：关联设计变更 BG-2026-002，需重新核验管线避让后的桩顶标高',
        inputValidator: (v) => (v && v.trim().length >= 6 ? true : '请填写不少于 6 个字的原因'),
      },
    )
    await designInputApi.unlock(projectId.value, reason)
    ElMessage.warning('已解锁，请尽快重新核验')
    await load()
  } catch (e) {
    if (e !== 'cancel' && e !== 'close') ElMessage.error(explainApiError(e))
  }
}

/** ---------------- STALE ---------------- */

async function doRefreshStale() {
  try {
    const r = await designInputApi.refreshStale(projectId.value)
    if (r.stale_count > 0) {
      ElMessage.warning(`${r.stale_count} 项参数的来源文件已更新，需重新核验`)
    } else {
      ElMessage.success('没有来源失效的参数')
    }
    await load()
  } catch (e) {
    ElMessage.error(explainApiError(e))
  }
}

/** ---------------- 来源抽屉 ---------------- */

const sourceDrawer = ref(false)
const sourceParam = ref<DesignParam | null>(null)

function showSource(p: DesignParam) {
  sourceParam.value = p
  sourceDrawer.value = true
}

async function relinkToLatest() {
  const p = sourceParam.value
  if (!p?.source?.latest_version_id) return
  try {
    await ElMessageBox.confirm(
      `把「${p.param_name}」的来源从 ${p.source.version_no} 改指到新版本 ` +
        `${p.source.latest_version_no}。\n\n改指后该参数会回到「待核验」状态，需要你确认新版本取值是否仍适用。`,
      '来源改指新版本',
      { confirmButtonText: '确认改指', cancelButtonText: '取消', type: 'warning' },
    )
  } catch {
    return
  }
  try {
    await designInputApi.relinkSource(projectId.value, p.id, p.source!.latest_version_id!)
    ElMessage.success('来源已更新，请重新核验取值')
    sourceDrawer.value = false
    await load()
  } catch (e) {
    ElMessage.error(explainApiError(e))
  }
}

/** 表格行样式：STALE 与 DOUBTFUL 高亮 */
function rowClass({ row }: { row: DesignParam }) {
  if (row.verify_status === VerifyStatus.STALE) return 'row-stale'
  if (row.verify_status === VerifyStatus.DOUBTFUL) return 'row-doubtful'
  return ''
}
</script>

<template>
  <div class="page">
    <!-- 顶部：汇总 + 操作 -->
    <div class="head app-card">
      <div class="head-l">
        <div class="sec-title" style="margin-bottom: 10px">
          设计输入
          <span class="more" @click="$router.push({ name: 'project-detail', params: { id: projectId } })">
            返回项目总览
          </span>
        </div>
        <p class="t-grey t-sm" style="margin: 0">
          <template v-if="tab === 'library'">
            设计人员查阅上游输入文件的入口 —— 勘察报告、试桩报告等都在这里，
            <b>可查看可下载</b>。文件本身的版本管理在「文件台账与追溯」里。
          </template>
          <template v-else>
            每个参数都可追溯到具体文件版本与页码表号。
            <template v-if="summary">
              共 {{ summary.total }} 项，其中必填 {{ summary.required_total }} 项。
            </template>
          </template>
        </p>
      </div>

      <div class="head-actions">
        <template v-if="tab === 'params'">
          <el-tag v-if="summary?.locked" type="success" effect="dark" size="large">
            已锁定
          </el-tag>
          <el-button v-if="!summary?.locked && summary?.can_lock && canEdit" type="primary" @click="doLock">
            锁定设计输入
          </el-button>
          <el-button v-if="summary?.locked && canEdit" @click="doUnlock">
            解锁（特权）
          </el-button>
          <el-button @click="doRefreshStale">检查来源失效</el-button>
        </template>
        <el-button v-else @click="loadLibrary">刷新</el-button>
      </div>
    </div>

    <!-- 一级切换：输入文件库（默认） / 参数溯源 -->
    <el-tabs v-model="tab" class="tabbar" @tab-change="onTabChange">
      <el-tab-pane label="输入文件库" name="library" />
      <el-tab-pane label="参数溯源" name="params" />
    </el-tabs>

    <!-- ============ 输入文件库 ============ -->
    <template v-if="tab === 'library'">
      <div class="stats">
        <div class="stat app-card">
          <div class="lab">可查阅输入文件</div>
          <div class="val t-blue">{{ libDocs.length }}</div>
          <div class="sub">勘察 / 前期调研 / 设计试桩等上游阶段</div>
        </div>
        <div class="stat app-card">
          <div class="lab">已发布（可作为设计依据）</div>
          <div class="val t-teal">{{ libPublished }}</div>
          <div class="sub">只有已发布版本才能被引用</div>
        </div>
        <div class="stat app-card" :class="{ alert: libInflight > 0 }">
          <div class="lab">签认中</div>
          <div class="val" :class="libInflight > 0 ? 't-amber' : 't-grey'">{{ libInflight }}</div>
          <div class="sub">尚未生效，请勿据此设计</div>
        </div>
        <div class="stat app-card">
          <div class="lab">可见阶段范围</div>
          <div class="val t-sm" style="font-weight: 600; line-height: 1.5; margin-top: 6px">
            按你的单位责任自动限定
          </div>
          <div class="sub">看不到的阶段不会出现在这里</div>
        </div>
      </div>

      <div class="app-card pad">
        <div class="sec-title">
          输入文件
          <span class="more" style="cursor: default">
            {{ libDocs.length }} 份 · 每份都标明主办单位与当前状态
          </span>
        </div>

        <el-skeleton v-if="libLoading" :rows="6" animated />
        <el-alert
          v-else-if="libError"
          :title="libError"
          type="error"
          show-icon
          :closable="false"
        />
        <el-table v-else :data="libDocs" size="small" style="width: 100%">
          <el-table-column label="文件" min-width="240">
            <template #default="{ row }">
              <div class="f-title">{{ row.title }}</div>
              <div class="t-grey t-sm t-mono">
                {{ row.doc_no || '无编号' }}
                <template v-if="row.category_name"> · {{ row.category_name }}</template>
              </div>
            </template>
          </el-table-column>
          <el-table-column label="阶段" width="104">
            <template #default="{ row }">
              <el-tag size="small" effect="plain">
                {{ row.stage_label || STAGE_LABEL[row.stage_code as never] || '—' }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="主办单位" width="126">
            <template #default="{ row }">
              <el-tag size="small" type="danger" effect="light">
                {{ row.primary_unit_label || '—' }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="当前版本 / 状态" width="150">
            <template #default="{ row }">
              <b class="t-mono">{{ row.effective_version_no || '—' }}</b>
              <el-tag
                :type="row.effective_state === 'PUBLISHED' ? 'success' : 'warning'"
                size="small"
                effect="light"
                style="margin-left: 5px"
              >
                {{ row.effective_state_label || '—' }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="上传人" width="120">
            <template #default="{ row }">
              <template v-if="row.current_uploaded_by?.name">
                <div>{{ row.current_uploaded_by.name }}</div>
                <div v-if="row.current_uploaded_by.employee_no" class="t-grey t-sm t-mono">
                  {{ row.current_uploaded_by.employee_no }}
                </div>
              </template>
              <span v-else class="t-grey t-sm">—</span>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="96" align="center">
            <template #default="{ row }">
              <el-button
                v-if="row.current_version_no"
                link
                type="primary"
                size="small"
                @click="downloadDoc(row)"
              >
                下载
              </el-button>
              <el-tooltip v-else content="尚未发布，无可下载版本" placement="top">
                <span class="t-grey t-sm">—</span>
              </el-tooltip>
            </template>
          </el-table-column>
        </el-table>

        <div v-if="!libLoading && !libError && !libDocs.length" class="empty t-grey">
          你的单位在本项目还没有可查阅的上游输入文件
        </div>
      </div>
    </template>

    <!-- ============ 参数溯源 ============ -->
    <template v-else>
    <!-- 核验进度 -->
    <div v-if="summary" class="stats">
      <div class="stat app-card">
        <div class="lab">核验进度</div>
        <div class="val t-teal">
          {{ summary.verified }}<span class="unit">/ {{ summary.total }}</span>
        </div>
        <div class="sub">必填 {{ summary.required_total }} 项</div>
      </div>
      <div class="stat app-card" :class="{ alert: summary.pending > 0 }">
        <div class="lab">待核验</div>
        <div class="val" :class="summary.pending > 0 ? 't-amber' : 't-grey'">
          {{ summary.pending }}
        </div>
        <div class="sub">未核验的必填项 {{ summary.unverified_required_count }} 项</div>
      </div>
      <div class="stat app-card" :class="{ alert: summary.stale > 0 }">
        <div class="lab">来源已失效</div>
        <div class="val" :class="summary.stale > 0 ? 't-red' : 't-grey'">{{ summary.stale }}</div>
        <div class="sub">来源文件已发布新版本</div>
      </div>
      <div class="stat app-card" :class="{ alert: summary.doubtful > 0 }">
        <div class="lab">存疑</div>
        <div class="val" :class="summary.doubtful > 0 ? 't-amber' : 't-grey'">
          {{ summary.doubtful }}
        </div>
        <div class="sub">待资料提供方澄清</div>
      </div>
    </div>

    <!-- STALE 警告条 -->
    <el-alert
      v-if="hasStale"
      type="error"
      show-icon
      :closable="false"
      style="margin-top: 14px"
      title="有参数的来源文件已发布新版本，原核验结论不再成立"
    >
      <template #default>
        <div style="font-size: 12.5px; line-height: 1.7">
          共 <b>{{ summary?.stale }}</b> 项需要重新核验。这正是
          <b>「勘察报告更新了，设计却不知道」</b> 这个工程风险的防线 ——
          系统自动标记，不依赖人工记得去查。请逐项确认新版本取值是否仍适用。
        </div>
      </template>
    </el-alert>

    <el-skeleton v-if="loading" :rows="8" animated style="margin-top: 16px" />
    <el-alert v-else-if="error" :title="error" type="error" show-icon :closable="false" />

    <!-- 参数表（按三层结构分组） -->
    <template v-else>
      <div v-for="g in grouped" :key="g.name" class="group app-card">
        <div class="sec-title" style="margin-bottom: 0">
          {{ g.name }}
          <span class="more" style="cursor: default">
            {{ g.items.filter((i) => i.verify_status === 'VERIFIED').length }} / {{ g.items.length }} 已核验
          </span>
        </div>
        <el-table
          :data="g.items"
          size="small"
          style="width: 100%"
          :row-class-name="rowClass"
          :show-overflow-tooltip="false"
        >
          <el-table-column label="参数名" min-width="180">
            <template #default="{ row }">
              <span class="pname">{{ row.param_name }}</span>
              <el-tag v-if="row.required" size="small" type="danger" effect="plain" class="req">
                必填
              </el-tag>
              <div class="pcode t-mono t-grey">{{ row.param_code }}</div>
            </template>
          </el-table-column>

          <el-table-column label="数值" width="140">
            <template #default="{ row }">
              <span class="pv">{{ row.display_value }}</span>
            </template>
          </el-table-column>

          <el-table-column label="来源（可溯源）" min-width="240">
            <template #default="{ row }">
              <div v-if="row.source" class="src">
                <a class="lk" @click="showSource(row)">
                  {{ row.source.document_title || '来源文件' }}
                  <b>{{ row.source.version_no }}</b>
                  <template v-if="row.source.locator"> · {{ row.source.locator }}</template>
                </a>
                <!-- 来源已有新版本 —— 这就是 STALE 的视觉提示 -->
                <el-tag
                  v-if="row.source.has_newer_published"
                  size="small"
                  type="danger"
                  effect="light"
                  class="newer"
                  @click="showSource(row)"
                >
                  已有新版本 {{ row.source.latest_version_no }}
                </el-tag>
              </div>
              <span v-else-if="row.source_locator" class="t-grey t-sm">{{ row.source_locator }}</span>
              <span v-else class="t-grey t-sm">人工录入</span>
            </template>
          </el-table-column>

          <el-table-column label="核验状态" width="112">
            <template #default="{ row }">
              <el-tooltip v-if="row.verify_note" :content="row.verify_note" placement="top">
                <el-tag :type="VERIFY_STATUS_TAG[row.verify_status as VerifyStatus]" size="small" effect="light">
                  {{ VERIFY_STATUS_LABEL[row.verify_status as VerifyStatus] }}
                </el-tag>
              </el-tooltip>
              <el-tag v-else :type="VERIFY_STATUS_TAG[row.verify_status as VerifyStatus]" size="small" effect="light">
                {{ VERIFY_STATUS_LABEL[row.verify_status as VerifyStatus] }}
              </el-tag>
            </template>
          </el-table-column>

          <el-table-column label="核验人 / 时间" width="150">
            <template #default="{ row }">
              <div v-if="row.verified_by_name" class="t-sm">
                {{ row.verified_by_name }}
                <div class="t-grey">{{ formatDateTime(row.verified_at) }}</div>
              </div>
              <span v-else class="t-grey t-sm">—</span>
            </template>
          </el-table-column>

          <el-table-column label="操作" width="200" align="right">
            <template #default="{ row }">
              <template v-if="!row.locked && canEdit">
                <el-button
                  link
                  type="primary"
                  size="small"
                  :loading="acting === row.id"
                  @click="doVerify(row, 'verify')"
                >
                  {{ row.verify_status === 'STALE' ? '重新核验' : '核验通过' }}
                </el-button>
                <el-button link size="small" @click="doModify(row)">修改</el-button>
                <el-button link type="warning" size="small" @click="doDoubtful(row)">存疑</el-button>
              </template>
              <el-tooltip v-else-if="row.locked" content="设计输入已锁定，修改需走设计变更流程" placement="top">
                <span class="t-amber t-sm">已锁定</span>
              </el-tooltip>
              <span v-else class="t-grey t-sm">只读</span>
            </template>
          </el-table-column>
        </el-table>
      </div>

      <!-- 锁定说明 -->
      <div class="note" :class="summary?.locked ? 'locked' : 'unlocked'">
        <template v-if="summary?.locked">
          <b>设计输入已锁定。</b>
          锁定的含义是：<b>设计依据不再会被悄悄改动</b>。
          如需修改任何参数，必须发起设计变更，走审批流程后由系统统一解锁并留痕。
        </template>
        <template v-else>
          <b>设计输入尚未锁定。</b>
          <template v-if="summary && summary.unverified_required_count > 0">
            还有 <b>{{ summary.unverified_required_count }}</b> 项必填参数未通过核验，核验完成后才能锁定。
            <span class="t-grey">
              （{{ summary.unverified_required.slice(0, 4).map((p) => p.param_name).join('、') }}
              <template v-if="summary.unverified_required_count > 4"> 等</template>）
            </span>
          </template>
          <template v-else>全部必填参数已核验，可以锁定。</template>
        </template>
      </div>
    </template>

    <!-- 来源详情抽屉 -->
    <el-drawer v-model="sourceDrawer" title="参数来源" size="480px">
      <template v-if="sourceParam">
        <div class="drawer-param">
          <div class="dp-name">{{ sourceParam.param_name }}</div>
          <div class="dp-code t-mono t-grey">{{ sourceParam.param_code }}</div>
          <div class="dp-value">{{ sourceParam.display_value }}</div>
        </div>

        <el-descriptions v-if="sourceParam.source" :column="1" border size="small">
          <el-descriptions-item label="来源文件">
            {{ sourceParam.source.document_title || '—' }}
          </el-descriptions-item>
          <el-descriptions-item label="文件编号">
            <span class="t-mono">{{ sourceParam.source.doc_no || '—' }}</span>
          </el-descriptions-item>
          <el-descriptions-item label="文件类型">
            {{ sourceParam.source.category_name || '—' }}
          </el-descriptions-item>
          <el-descriptions-item label="版本">
            <b>{{ sourceParam.source.version_no }}</b>
            <el-tag size="small" effect="plain" style="margin-left: 6px">
              {{ DOCUMENT_STATE_LABEL[sourceParam.source.state] }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="定位（页码/表号）">
            <b>{{ sourceParam.source.locator || '—' }}</b>
          </el-descriptions-item>
        </el-descriptions>

        <el-alert
          v-if="sourceParam.source?.has_newer_published"
          type="error"
          show-icon
          :closable="false"
          style="margin-top: 14px"
          title="来源文件已发布新版本"
        >
          <div style="font-size: 12.5px; line-height: 1.7; margin-bottom: 10px">
            本参数当前引用 <b>{{ sourceParam.source.version_no }}</b>，
            但该文件已发布 <b>{{ sourceParam.source.latest_version_no }}</b>。
            原核验结论基于旧版本，<b>不再成立</b>，需重新核验。
          </div>
          <el-button type="primary" size="small" @click="relinkToLatest">
            改指到 {{ sourceParam.source.latest_version_no }} 并重新核验
          </el-button>
        </el-alert>

        <div v-else-if="sourceParam.source" class="ok-note">
          来源为当前有效版本，无需处理。
        </div>

        <div v-if="sourceParam.verify_note" class="note-block">
          <div class="nb-title">核验说明</div>
          {{ sourceParam.verify_note }}
        </div>
      </template>
    </el-drawer>
    </template>
  </div>
</template>

<style scoped>
.page {
  max-width: 1680px;
}

/* ---------------- 一级切换 ---------------- */
.tabbar {
  margin: 14px 0 0;
  padding: 0 18px;
  background: #fff;
  border: 1px solid var(--line);
  border-radius: 8px 8px 0 0;
  border-bottom: none;
}
.pad {
  padding: 16px 20px;
  margin-top: 0;
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
  gap: 10px;
  flex: 0 0 auto;
}

.stats {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 14px;
  margin-top: 14px;
}
.stat {
  padding: 14px 16px;
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
  font-size: 24px;
  font-weight: 700;
  margin-top: 4px;
  letter-spacing: -0.5px;
}
.stat .val .unit {
  font-size: 13px;
  font-weight: 400;
  color: var(--grey);
}
.stat .sub {
  font-size: 12px;
  color: var(--grey);
  margin-top: 3px;
}

.group {
  margin-top: 16px;
  padding: 14px 18px 6px;
}

.pname {
  font-weight: 600;
  color: var(--ink);
}
.req {
  margin-left: 6px;
  transform: scale(0.85);
}
.pcode {
  font-size: 11px;
  margin-top: 1px;
}
.pv {
  font-weight: 700;
  color: var(--blue);
}

.src {
  display: flex;
  flex-direction: column;
  gap: 3px;
}
.lk {
  color: var(--blue);
  cursor: pointer;
  font-size: 12.5px;
}
.lk:hover {
  text-decoration: underline;
}
.newer {
  cursor: pointer;
  align-self: flex-start;
}

/* 行高亮：STALE 与 DOUBTFUL 必须一眼看到 */
:deep(.row-stale) {
  background: #fdf1f1 !important;
}
:deep(.row-doubtful) {
  background: #fffaf0 !important;
}

.note {
  margin-top: 16px;
  border-radius: 6px;
  padding: 12px 16px;
  font-size: 12.5px;
  line-height: 1.8;
}
.note.locked {
  background: var(--teal-soft);
  border: 1px solid #b8e0db;
  color: #0b6b62;
}
.note.unlocked {
  background: #fffaf0;
  border: 1px solid #f0dcb0;
  color: #7a5a17;
}
.note b {
  font-weight: 700;
}

/* 抽屉 */
.drawer-param {
  padding-bottom: 14px;
  border-bottom: 1px solid var(--line);
  margin-bottom: 16px;
}
.dp-name {
  font-size: 16px;
  font-weight: 700;
}
.dp-code {
  font-size: 11.5px;
  margin: 2px 0 8px;
}
.dp-value {
  font-size: 20px;
  font-weight: 700;
  color: var(--blue);
}
.ok-note {
  margin-top: 14px;
  background: var(--teal-soft);
  border: 1px solid #b8e0db;
  color: #0b6b62;
  border-radius: 5px;
  padding: 10px 13px;
  font-size: 12.5px;
}
.note-block {
  margin-top: 14px;
  background: #f7f9fc;
  border: 1px solid var(--line);
  border-radius: 5px;
  padding: 10px 13px;
  font-size: 12.5px;
  color: var(--ink-2);
  line-height: 1.7;
}
.nb-title {
  font-weight: 700;
  color: var(--grey);
  font-size: 11.5px;
  margin-bottom: 4px;
}
</style>
