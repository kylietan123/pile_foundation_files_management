<script setup lang="ts">
/**
 * 桩基选型（设计阶段）。
 *
 * 把原来独立的「选型」软件里最有价值的那部分搬进来：
 *   项目条件 + 勘察承载力表 → 桩型评分排序 → 建议桩参数 → 人工校对 → 确认留痕。
 *
 * 设计取舍：
 *   - 规则引擎在后端（`app/services/pile_selection.py`），前端只做展示与校对，
 *     不重复实现一套打分，避免"两处算法打架"；
 *   - 试算（POST /suggest）不落库，只有"保存 / 确认"才写库，便于反复调条件；
 *   - 切换桩型时用后端下发的典型参数组合就地重填，保证口径唯一。
 */
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'

import { pileSelectionApi } from '@/api'
import { explainApiError } from '@/api/http'
import type {
  PileCalcInputs,
  PileCapacityRow,
  PileConditions,
  PileOverview,
  PileParams,
  PileSelectionOptions,
  PileSelectionRecord,
  PileSuggestion,
  ProjectInfo,
} from '@/api/types'
import { useAuthStore } from '@/stores/auth'
import { useProjectStore } from '@/stores/project'
import StageContextBar from '@/components/StageContextBar.vue'

const route = useRoute()
const auth = useAuthStore()
const projectStore = useProjectStore()

const projectId = computed(() => route.params.id as string)
const stage = computed(() => (route.query.stage as string) || 'DESIGN')

const loading = ref(false)
const options = ref<PileSelectionOptions | null>(null)
const error = ref<string | null>(null)

const suggesting = ref(false)
const saving = ref(false)
const suggestion = ref<PileSuggestion | null>(null)
const saved = ref<PileSelectionRecord | null>(null)

/* ---------------- 一、建筑概况（原软件第一步） ---------------- */
const blankOverview = (): PileOverview => ({
  project_name: '',
  volume_ratio: null,
  plots: [{ land_area_m2: null, aboveground_area_m2: null, underground_area_m2: null, total_area_m2: null }],
  tower_count: null,
  towers: [],
  height_range: '',
  basement_floors: 2,
  basement_heights_m: [4, 4],
  cover_thick_m: 1.5,
  indoor_outdoor_diff_m: 0.15,
  slab_top_m: 0.4,
  slab_mid_m: 0.25,
  slab_bottom_single_m: 0.6,
  slab_bottom_double_m: 0.8,
})
const overview = reactive<PileOverview>(blankOverview())

/** 地上层数输入（"1,11,14" → towers），避免让用户在表格里一行行加 */
const floorsText = ref('')

/* ---------------- 二、非主楼数据（CAD 实测） ---------------- */
const calcInputs = reactive<PileCalcInputs>({
  single_area_m2: null,
  double_area_m2: null,
  tower_single_m2: null,
  tower_double_m2: null,
  grid_x_m: 6,
  grid_y_m: 6,
  aboveground_double_m2: null,
})

/* ---------------- 三、项目条件 ---------------- */
const conditions = reactive<PileConditions>({
  metro_protection_zone: false,
  inner_ring: false,
  near_viaduct_bridge: false,
  dense_buildings_nearby: false,
  noise_sensitive: false,
  tight_schedule: false,
  tight_budget: false,
  env_protection_strict: false,
  has_sand_layer: false,
  need_permanent_temp_combo: false,
  has_inner_support: false,
  basement_floors: 2,
  tower_max_floors: null,
  tower_max_height_m: null,
})

/* ---------------- 四、勘察承载力表 ---------------- */
const capacityRows = ref<PileCapacityRow[]>([])

/* ---------------- 报告 ---------------- */
const reportForm = reactive({
  report_title: '桩基评估',
  date: '',
  basis_files: '',
})
const reportText = ref('')
const reportBusy = ref(false)

/** 校对表结论 */
const mainChoice = reactive<{ type_name: string; params: PileParams }>({
  type_name: '',
  params: {},
})
const baseChoice = reactive<{ type_name: string; params: PileParams }>({
  type_name: '',
  params: {},
})

const reason = ref('')

const project = computed<ProjectInfo | null>(() => projectStore.current ?? null)

/** 我在本项目设计阶段能否编辑（体验层，真正拦截在后端） */
const canEdit = computed(
  () => auth.membershipOf(projectId.value)?.actions.includes('EDIT') ?? false,
)

const restricted = computed(() =>
  ['metro_protection_zone', 'inner_ring', 'near_viaduct_bridge', 'dense_buildings_nearby'].some(
    (k) => conditions[k as keyof PileConditions],
  ),
)

/**
 * 这次结论有没有**勘察数据**支撑。
 *
 * 规则引擎在没有勘察表时也能算（用典型组合 = 历史项目经验值），
 * 但那是"方案初判"，不是"设计依据"。界面必须把这层说清楚，
 * 否则用户会以为系统凭空给出了结论。
 */
const hasSurveyBasis = computed(() => {
  const s = suggestion.value
  if (!s) return false
  return s.basis === 'survey' || !!(s.main.params.from_row || s.base.params.from_row)
})

/** 缺依据的桩型（用于提示具体差哪一边） */
const lackingRoles = computed(() => {
  const s = suggestion.value
  if (!s) return []
  const out: string[] = []
  if (!s.main.params.from_row) out.push('主楼')
  if (!s.base.params.from_row) out.push('纯地下室')
  return out
})

onMounted(async () => {
  if (!projectStore.current || projectStore.current.id !== projectId.value) {
    await projectStore.fetchDetail(projectId.value).catch(() => undefined)
  }
  await loadOptions()
  await loadSaved()
})

async function loadOptions() {
  try {
    options.value = await pileSelectionApi.options(projectId.value)
  } catch (e) {
    error.value = explainApiError(e)
  }
}

async function loadSaved() {
  loading.value = true
  try {
    saved.value = await pileSelectionApi.get(projectId.value)
    if (saved.value) {
      Object.assign(conditions, saved.value.conditions || {})
      capacityRows.value = (saved.value.geo?.capacity_rows || []).map((r) => ({ ...r }))
      if (saved.value.overview) {
        Object.assign(overview, saved.value.overview)
        floorsText.value = (saved.value.overview.towers || [])
          .map((t) => t.floors)
          .filter(Boolean)
          .join(',')
      }
      if (saved.value.calc_inputs) Object.assign(calcInputs, saved.value.calc_inputs)
      mainChoice.type_name = saved.value.main?.type_name || ''
      mainChoice.params = { ...(saved.value.main?.params || {}) }
      baseChoice.type_name = saved.value.base?.type_name || ''
      baseChoice.params = { ...(saved.value.base?.params || {}) }
      reason.value = saved.value.reason || ''
      suggestion.value = saved.value.snapshot || null
      reportText.value = saved.value.report_text || ''
      const meta = (saved.value.report_meta || {}) as Record<string, string>
      if (meta.report_title) reportForm.report_title = meta.report_title
      if (meta.date) reportForm.date = meta.date
      if (Array.isArray(saved.value.report_meta?.basis_files)) {
        reportForm.basis_files = (saved.value.report_meta?.basis_files as string[]).join('\n')
      }
    }
  } catch (e) {
    error.value = explainApiError(e)
  } finally {
    loading.value = false
  }
}

/** 把"1,11,14"解析成塔楼数组，同时把最大层数同步给项目条件（桩径规则要用） */
function syncTowers() {
  const nums = floorsText.value
    .split(/[,，、\s]+/)
    .map((s) => Number(s.trim()))
    .filter((n) => Number.isFinite(n) && n > 0)
  overview.towers = nums.map((f) => ({ floors: f }))
  if (nums.length) conditions.tower_max_floors = Math.max(...nums)
}

/** 概况里的地下室层数同步到项目条件（抗浮需求按层数选公式） */
function syncBasement() {
  conditions.basement_floors = overview.basement_floors ?? 2
  const n = Math.max(1, Math.min(3, overview.basement_floors ?? 1))
  overview.basement_heights_m = Array.from({ length: n }, (_, i) =>
    overview.basement_heights_m?.[i] ?? 4,
  )
}

/**
 * 填入「古美」样例数据（与原选型软件的样例按钮同一套数）。
 *
 * 实测路径：点它 → 试算 → 保存草稿/确认 → 生成报告，
 * 出来的报告应当与历史交付报告逐字一致（见 scripts/test_pile_report.py）。
 */
function fillGumeiSample() {
  Object.assign(overview, {
    project_name: '闵行古美-31-02地块',
    volume_ratio: 2.0,
    plots: [
      {
        land_area_m2: 31521,
        aboveground_area_m2: 67400,
        underground_area_m2: 32895,
        total_area_m2: 100295,
      },
    ],
    tower_count: 12,
    height_range: '5m~50m',
    basement_floors: 2,
    basement_heights_m: [4, 4],
    cover_thick_m: 1.5,
    indoor_outdoor_diff_m: 0.15,
    slab_top_m: 0.4,
    slab_mid_m: 0.25,
    slab_bottom_single_m: 0.6,
    slab_bottom_double_m: 0.8,
  })
  floorsText.value = '1,11,14'
  syncTowers()
  syncBasement()
  Object.assign(calcInputs, {
    single_area_m2: 20017,
    double_area_m2: 6115,
    tower_single_m2: 9500,
    tower_double_m2: 1950,
    grid_x_m: 6,
    grid_y_m: 6,
    aboveground_double_m2: 12200,
  })
  ElMessage.success('已填入古美样例数据（无地铁保护区，地下 2 层）')
}

function overviewPayload(): PileOverview {
  syncTowers()
  syncBasement()
  return {
    ...overview,
    plots: (overview.plots || []).length ? overview.plots : [],
  }
}

function calcPayload(): PileCalcInputs | null {
  const any = Object.values(calcInputs).some((v) => v !== null && v !== undefined && v !== 0)
  return any ? { ...calcInputs } : null
}

function reportPayload() {
  return {
    overview: overviewPayload(),
    calc_inputs: calcPayload(),
    report_title: reportForm.report_title || '桩基评估',
    date: reportForm.date || null,
    basis_files: reportForm.basis_files
      .split('\n')
      .map((s) => s.trim())
      .filter(Boolean),
    project_name: overview.project_name || null,
  }
}

async function generateReport() {
  if (!saved.value) {
    ElMessage.warning('请先试算并保存选型方案，再生成评估报告')
    return
  }
  reportBusy.value = true
  try {
    const res = await pileSelectionApi.saveReport(projectId.value, reportPayload())
    reportText.value = res.text
    ElMessage.success(`报告已生成（${res.char_count} 字）`)
  } catch (e) {
    ElMessage.error(explainApiError(e))
  } finally {
    reportBusy.value = false
  }
}

function openReport(saveAs = false) {
  window.open(pileSelectionApi.reportUrl(projectId.value, saveAs), '_blank')
}

function addRow() {
  capacityRows.value.push({
    pile_type_desc: '',
    d_mm: null,
    length_m: null,
    bearing_layer_id: '',
    ra_kn: null,
    rd_kn: null,
    rtd_kn: null,
    note: '',
  })
}

function removeRow(index: number) {
  capacityRows.value.splice(index, 1)
}

function geoPayload() {
  const rows = capacityRows.value.filter(
    (r) => (r.pile_type_desc || '').trim() || r.d_mm || r.ra_kn || r.rd_kn || r.rtd_kn,
  )
  if (!rows.length) return null
  return { capacity_rows: rows, strata: [], bearing_layer_id: null }
}

async function runSuggest() {
  suggesting.value = true
  try {
    const result = await pileSelectionApi.suggest(projectId.value, {
      conditions: { ...conditions },
      geo: geoPayload(),
    })
    suggestion.value = result
    mainChoice.type_name = result.main.type_name
    mainChoice.params = { ...result.main.params }
    baseChoice.type_name = result.base.type_name
    baseChoice.params = { ...result.base.params }
    reason.value = ''
    ElMessage.success('已按当前条件算出建议，请在下方校对确认')
  } catch (e) {
    ElMessage.error(explainApiError(e))
  } finally {
    suggesting.value = false
  }
}
/** 切桩型：用后端典型参数组合就地重填（口径唯一，不在前端另写一套） */
function onTypeChange(role: 'main' | 'base', code: string) {
  const t = options.value?.pile_types.find((x) => x.code === code)
  const floors = conditions.basement_floors ?? 2
  const key = role === 'main' ? 'main' : floors >= 2 ? 'base_B2' : 'base_B1'
  const combo = (t?.combos || {})[key] || {}
  const target = role === 'main' ? mainChoice : baseChoice
  target.type_name = code
  target.params = { ...combo }
}

async function persist(status: 'DRAFT' | 'CONFIRMED') {
  if (!mainChoice.type_name || !baseChoice.type_name) {
    ElMessage.warning('请先试算出建议，或在校对表里选择桩型')
    return
  }
  if (status === 'CONFIRMED' && !hasSurveyBasis.value) {
    ElMessage.warning(
      '没有勘察依据不能确认：请先把勘察报告的承载力估算表录入「四、勘察承载力表」，或只保存草稿',
    )
    return
  }
  if (status === 'CONFIRMED') {
    try {
      await ElMessageBox.confirm(
        '确认后，本方案将作为设计阶段桩基选型的依据（可再次修改并重新确认）。',
        '确认选型方案',
        { confirmButtonText: '确认', cancelButtonText: '再看看', type: 'warning' },
      )
    } catch {
      return
    }
  }
  saving.value = true
  try {
    const payload = {
      conditions: { ...conditions },
      geo: geoPayload(),
      overview: overviewPayload(),
      calc_inputs: calcPayload(),
      main: { type_name: mainChoice.type_name, params: mainChoice.params },
      base: { type_name: baseChoice.type_name, params: baseChoice.params },
      reason: reason.value || null,
      status,
    }
    saved.value = await pileSelectionApi.save(projectId.value, payload)
    reason.value = saved.value.reason || ''
    ElMessage.success(status === 'CONFIRMED' ? '选型方案已确认' : '已保存草稿')
  } catch (e) {
    ElMessage.error(explainApiError(e))
  } finally {
    saving.value = false
  }
}

const statusLabel = computed(() => {
  if (!saved.value) return '未保存'
  return saved.value.status === 'CONFIRMED' ? '已确认' : '草稿'
})

function condLabel(key: string) {
  return options.value?.conditions.find((c) => c.key === key)?.label ?? key
}

function rankingOf(role: 'main' | 'base') {
  return suggestion.value?.[role]?.ranking ?? []
}

function rowTags(r: PileParams) {
  const tags: string[] = []
  if (r.from_row) tags.push('取自勘察表')
  if (r.from_interp) tags.push('线插法')
  if (r.from_row === false) tags.push('无勘察依据 · 典型组合')
  return tags
}
</script>

<template>
  <div class="page">
    <StageContextBar :project-id="projectId" :stage="stage" active="pile-selection" />

    <!-- 页头 -->
    <div class="head app-card">
      <div class="head-l">
        <div class="sec-title">
          桩基选型
          <el-tag size="small" :type="saved?.status === 'CONFIRMED' ? 'success' : 'info'" style="margin-left: 8px">
            {{ statusLabel }}
          </el-tag>
          <span class="more" @click="$router.push({ name: 'project-detail', params: { id: projectId } })">
            返回项目总览
          </span>
        </div>
      </div>
      <div class="head-actions">
        <el-button v-if="saved?.status === 'CONFIRMED'" class="confirmed-hint" text type="success">
          由 {{ saved.confirmed_by_name || '—' }} 确认
        </el-button>
        <el-button :loading="suggesting" type="primary" :disabled="!canEdit" @click="runSuggest">
          试算选型建议
        </el-button>
      </div>
    </div>

    <el-alert v-if="error" :title="error" type="error" show-icon :closable="false" />
    <el-alert
      v-if="!canEdit && !error"
      title="你在设计阶段只是参与身份，只能查看。"
      type="info"
      show-icon
      :closable="false"
    />

    <!-- 一、建筑概况 -->
    <section class="app-card block">
      <div class="block-head">
        <strong>一、建筑概况</strong>
        <el-button
          v-if="canEdit"
          size="small"
          text
          type="primary"
          style="margin-left: auto"
          @click="fillGumeiSample"
        >
          填入古美样例
        </el-button>
      </div>
      <div class="form-grid">
        <el-form-item label="项目名称">
          <el-input v-model="overview.project_name" placeholder="如：闵行古美-31-02地块" :disabled="!canEdit" />
        </el-form-item>
        <el-form-item label="容积率">
          <el-input-number v-model="overview.volume_ratio" :min="0" :step="0.1" :precision="1" style="width: 100%" :disabled="!canEdit" />
        </el-form-item>
        <el-form-item label="规划用地面积 (m²)">
          <el-input-number v-model="overview.plots[0].land_area_m2" :min="0" :step="100" style="width: 100%" :disabled="!canEdit" />
        </el-form-item>
        <el-form-item label="地上建筑面积 (m²)">
          <el-input-number v-model="overview.plots[0].aboveground_area_m2" :min="0" :step="100" style="width: 100%" :disabled="!canEdit" />
        </el-form-item>
        <el-form-item label="地下建筑面积 (m²)">
          <el-input-number v-model="overview.plots[0].underground_area_m2" :min="0" :step="100" style="width: 100%" :disabled="!canEdit" />
        </el-form-item>
        <el-form-item label="总建筑面积 (m²)">
          <el-input-number v-model="overview.plots[0].total_area_m2" :min="0" :step="100" style="width: 100%" :disabled="!canEdit" />
        </el-form-item>
        <el-form-item label="住宅单体数量">
          <el-input-number v-model="overview.tower_count" :min="0" :step="1" style="width: 100%" :disabled="!canEdit" />
        </el-form-item>
        <el-form-item label="地上层数（逗号分隔）">
          <el-input v-model="floorsText" placeholder="1,11,14" :disabled="!canEdit" @change="syncTowers" />
        </el-form-item>
        <el-form-item label="高度范围">
          <el-input v-model="overview.height_range" placeholder="5m~50m" :disabled="!canEdit" />
        </el-form-item>
        <el-form-item label="地下层数">
          <el-input-number v-model="overview.basement_floors" :min="0" :max="5" style="width: 100%" :disabled="!canEdit" @change="syncBasement" />
        </el-form-item>
        <el-form-item label="地下室层高 (m，逗号分隔)">
          <el-input
            :model-value="(overview.basement_heights_m || []).join(',')"
            placeholder="4,4"
            :disabled="!canEdit"
            @update:model-value="(v: string) => {
              overview.basement_heights_m = v.split(/[,，、\s]+/).map(Number).filter((n) => Number.isFinite(n) && n > 0)
            }"
          />
        </el-form-item>
        <el-form-item label="顶板覆土厚度 (m)">
          <el-input-number v-model="overview.cover_thick_m" :min="0" :step="0.1" :precision="2" style="width: 100%" :disabled="!canEdit" />
        </el-form-item>
        <el-form-item label="室内外高差 (m)">
          <el-input-number v-model="overview.indoor_outdoor_diff_m" :min="0" :step="0.05" :precision="2" style="width: 100%" :disabled="!canEdit" />
        </el-form-item>
        <el-form-item label="顶板折算厚度 (m)">
          <el-input-number v-model="overview.slab_top_m" :min="0" :step="0.05" :precision="2" style="width: 100%" :disabled="!canEdit" />
        </el-form-item>
        <el-form-item label="中板折算厚度 (m)">
          <el-input-number v-model="overview.slab_mid_m" :min="0" :step="0.05" :precision="2" style="width: 100%" :disabled="!canEdit" />
        </el-form-item>
        <el-form-item label="单层底板 (m)">
          <el-input-number v-model="overview.slab_bottom_single_m" :min="0" :step="0.05" :precision="2" style="width: 100%" :disabled="!canEdit" />
        </el-form-item>
        <el-form-item label="双层底板 (m)">
          <el-input-number v-model="overview.slab_bottom_double_m" :min="0" :step="0.05" :precision="2" style="width: 100%" :disabled="!canEdit" />
        </el-form-item>
      </div>
    </section>

    <!-- 二、项目条件 -->
    <section class="app-card block">
      <div class="block-head">
        <strong>二、项目条件</strong>
      </div>
      <div class="cond-grid">
        <label
          v-for="c in options?.conditions || []"
          :key="c.key"
          class="cond"
          :class="{ hard: c.hard, on: !!conditions[c.key as keyof PileConditions] }"
        >
          <el-checkbox
            v-model="conditions[c.key as keyof PileConditions] as boolean"
            :disabled="!canEdit"
          >
            {{ c.label }}
            <el-tag v-if="c.hard" size="small" type="danger" effect="plain">硬性</el-tag>
          </el-checkbox>
        </label>
      </div>
      <div class="num-grid">
        <div class="num-item">
          <span>地下室层数</span>
          <el-input-number v-model="conditions.basement_floors" :min="0" :max="5" size="small" :disabled="!canEdit" />
        </div>
        <div class="num-item">
          <span>塔楼最高层数</span>
          <el-input-number v-model="conditions.tower_max_floors" :min="0" :max="200" size="small" :disabled="!canEdit" />
        </div>
        <div class="num-item">
          <span>塔楼最大高度 (m)</span>
          <el-input-number v-model="conditions.tower_max_height_m" :min="0" :max="1000" size="small" :disabled="!canEdit" />
        </div>
        <div class="num-item scene">
          <span>场景判定</span>
          <el-tag :type="restricted ? 'warning' : 'success'" effect="plain">
            {{ restricted ? '受限场景（挤土桩排除）' : '经济场景（成本/工期主导）' }}
          </el-tag>
        </div>
      </div>
    </section>

    <!-- 三、非主楼数据（CAD 实测；无地下室可整体留空） -->
    <el-collapse class="geo-collapse">
      <el-collapse-item name="calc">
        <template #title>
          <strong>三、非主楼数据</strong>
        </template>
        <div class="form-grid">
          <el-form-item label="纯单层地下室投影面积 (m²)">
            <el-input-number v-model="calcInputs.single_area_m2" :min="0" :step="100" style="width: 100%" :disabled="!canEdit" />
          </el-form-item>
          <el-form-item label="纯双层地下室投影面积 (m²)">
            <el-input-number v-model="calcInputs.double_area_m2" :min="0" :step="100" style="width: 100%" :disabled="!canEdit" />
          </el-form-item>
          <el-form-item label="单层范围内塔楼投影 (m²)">
            <el-input-number v-model="calcInputs.tower_single_m2" :min="0" :step="100" style="width: 100%" :disabled="!canEdit" />
          </el-form-item>
          <el-form-item label="双层范围内塔楼投影 (m²)">
            <el-input-number v-model="calcInputs.tower_double_m2" :min="0" :step="100" style="width: 100%" :disabled="!canEdit" />
          </el-form-item>
          <el-form-item label="柱网尺寸 X (m)">
            <el-input-number v-model="calcInputs.grid_x_m" :min="0" :step="0.5" style="width: 100%" :disabled="!canEdit" />
          </el-form-item>
          <el-form-item label="柱网尺寸 Y (m)">
            <el-input-number v-model="calcInputs.grid_y_m" :min="0" :step="0.5" style="width: 100%" :disabled="!canEdit" />
          </el-form-item>
          <el-form-item label="双层范围内主楼地上建面 (m²)">
            <el-input-number v-model="calcInputs.aboveground_double_m2" :min="0" :step="100" style="width: 100%" :disabled="!canEdit" />
          </el-form-item>
        </div>
      </el-collapse-item>
    </el-collapse>

    <!-- 四、勘察承载力表（可选） -->
    <el-collapse class="geo-collapse">
      <el-collapse-item name="geo">
        <template #title>
          <strong>四、勘察承载力表</strong>
          <span v-if="capacityRows.length" class="t-grey t-sm" style="margin-left: 8px">
            已录入 {{ capacityRows.length }} 行
          </span>
        </template>
        <el-table :data="capacityRows" size="small" border empty-text="尚未录入勘察承载力行">
          <el-table-column label="桩型描述" min-width="170">
            <template #default="{ row }">
              <el-input v-model="row.pile_type_desc" size="small" placeholder="Ф800钻孔灌注桩" :disabled="!canEdit" />
            </template>
          </el-table-column>
          <el-table-column label="桩径 mm" width="100">
            <template #default="{ row }">
              <el-input-number v-model="row.d_mm" :min="0" :step="50" size="small" controls-position="right" :disabled="!canEdit" />
            </template>
          </el-table-column>
          <el-table-column label="桩长 m" width="100">
            <template #default="{ row }">
              <el-input-number v-model="row.length_m" :min="0" :step="1" size="small" controls-position="right" :disabled="!canEdit" />
            </template>
          </el-table-column>
          <el-table-column label="持力层" width="100">
            <template #default="{ row }">
              <el-input v-model="row.bearing_layer_id" size="small" placeholder="⑦₂" :disabled="!canEdit" />
            </template>
          </el-table-column>
          <el-table-column label="Ra (kN)" width="105">
            <template #default="{ row }">
              <el-input-number v-model="row.ra_kn" :min="0" :step="10" size="small" controls-position="right" :disabled="!canEdit" />
            </template>
          </el-table-column>
          <el-table-column label="Rd (kN)" width="105">
            <template #default="{ row }">
              <el-input-number v-model="row.rd_kn" :min="0" :step="10" size="small" controls-position="right" :disabled="!canEdit" />
            </template>
          </el-table-column>
          <el-table-column label="Rtd (kN)" width="105">
            <template #default="{ row }">
              <el-input-number v-model="row.rtd_kn" :min="0" :step="10" size="small" controls-position="right" :disabled="!canEdit" />
            </template>
          </el-table-column>
          <el-table-column label="" width="60" align="center">
            <template #default="{ $index }">
              <el-button v-if="canEdit" text type="danger" size="small" @click="removeRow($index)">删</el-button>
            </template>
          </el-table-column>
        </el-table>
        <el-button v-if="canEdit" size="small" style="margin-top: 10px" @click="addRow">+ 添加一行</el-button>
      </el-collapse-item>
    </el-collapse>

    <!-- 建议与校对 -->
    <el-skeleton v-if="loading" :rows="6" animated class="skeleton" />

    <template v-else-if="suggestion">
      <el-alert
        v-if="!hasSurveyBasis"
        title="未使用勘察数据：桩长与承载力为典型组合，不能确认方案"
        type="warning"
        show-icon
        :closable="false"
        class="basis-alert"
      />
      <el-alert
        v-else-if="lackingRoles.length"
        :title="`「${lackingRoles.join('、')}」未匹配到勘察表行，参数为典型组合`"
        type="info"
        show-icon
        :closable="false"
        class="basis-alert"
      />

      <section class="app-card block">
        <div class="block-head">
          <strong>五、选型建议与校对</strong>
          <span class="t-grey t-sm">
            {{ suggestion.scenario === 'restricted' ? '受限场景' : '经济场景' }}
            <template v-if="suggestion.restrictions.length">
              · {{ suggestion.restrictions.join('、') }}
            </template>
          </span>
        </div>

        <div class="role-grid">
          <div v-for="role in (['main', 'base'] as const)" :key="role" class="role-card">
            <div class="role-head">
              <span class="role-name">{{ role === 'main' ? '主楼承压桩' : '纯地下室桩' }}</span>
              <el-tag
                v-if="suggestion[role].diameter_rule"
                size="small"
                type="primary"
                effect="plain"
              >
                选型图桩径 Φ{{ suggestion[role].diameter_rule }}
              </el-tag>
            </div>

            <el-select
              :model-value="role === 'main' ? mainChoice.type_name : baseChoice.type_name"
              size="small"
              filterable
              style="width: 100%"
              :disabled="!canEdit"
              @change="(v: string) => onTypeChange(role, v)"
            >
              <el-option
                v-for="t in options?.pile_types || []"
                :key="t.code"
                :label="`${t.label}（${t.category}）`"
                :value="t.code"
              >
                <span>{{ t.label }}</span>
                <span class="opt-hint">{{ t.category }}</span>
                <el-tag v-if="t.not_considered" size="small" type="info" effect="plain" style="margin-left: 6px">
                  暂不考虑
                </el-tag>
              </el-option>
            </el-select>

            <div class="param-grid">
              <div><span>桩径</span><b>{{ (role === 'main' ? mainChoice : baseChoice).params.d_mm ?? '—' }} mm</b></div>
              <div><span>桩长</span><b>{{ (role === 'main' ? mainChoice : baseChoice).params.lengths ?? '—' }}</b></div>
              <div>
                <span>{{ role === 'main' ? '抗压承载力' : '抗拔承载力' }}</span>
                <b>
                  {{
                    role === 'main'
                      ? (mainChoice.params.capacity_t ?? '—')
                      : (baseChoice.params.uplift_t ?? '—')
                  }} t
                </b>
              </div>
              <div><span>持力层</span><b>{{ (role === 'main' ? mainChoice : baseChoice).params.layer_desc || (role === 'main' ? mainChoice : baseChoice).params.layer || '—' }}</b></div>
            </div>

            <div class="param-desc">
              {{ (role === 'main' ? mainChoice : baseChoice).params.desc || '—' }}
            </div>

            <div class="param-tags">
              <el-tag
                v-for="tg in rowTags((role === 'main' ? mainChoice : baseChoice).params)"
                :key="tg"
                size="small"
                :type="tg.includes('无勘察依据') ? 'warning' : 'success'"
                effect="plain"
              >
                {{ tg }}
              </el-tag>
              <span v-if="(role === 'main' ? mainChoice : baseChoice).params.note" class="t-amber t-sm">
                {{ (role === 'main' ? mainChoice : baseChoice).params.note }}
              </span>
            </div>

            <!-- 可手工微调 -->
            <div v-if="canEdit" class="manual-grid">
              <el-input-number
                v-model="((role === 'main' ? mainChoice : baseChoice).params.d_mm as number)"
                :min="0" :step="50" size="small" controls-position="right"
              />
              <el-input
                v-model="((role === 'main' ? mainChoice : baseChoice).params.lengths as string)"
                size="small" placeholder="桩长，如 45m"
              />
              <el-input-number
                v-if="role === 'main'"
                v-model="(mainChoice.params.capacity_t as number)"
                :min="0" :step="10" size="small" controls-position="right"
              />
              <el-input-number
                v-else
                v-model="(baseChoice.params.uplift_t as number)"
                :min="0" :step="10" size="small" controls-position="right"
              />
            </div>
          </div>
        </div>
      </section>

      <!-- 排序明细 -->
      <section class="app-card block">
        <div class="block-head">
          <strong>六、各桩型评分明细</strong>
        </div>
        <div class="rank-grid">
          <div v-for="role in (['main', 'base'] as const)" :key="role" class="rank-card">
            <div class="rank-title">{{ role === 'main' ? '主楼' : '地下室' }}</div>
            <div class="rank-row" v-for="(r, i) in rankingOf(role)" :key="r.name">
              <span class="idx">{{ String(i + 1).padStart(2, '0') }}</span>
              <span class="name" :class="{ dim: r.hard_excluded || r.not_considered }">{{ r.label }}</span>
              <span class="cat">{{ r.category }}</span>
              <b v-if="!r.hard_excluded && !r.not_considered" class="score">{{ r.total }}</b>
              <span v-else class="reason">{{ r.reason }}</span>
            </div>
          </div>
        </div>
      </section>

      <!-- 理由与保存 -->
      <section class="app-card block">
        <div class="block-head">
          <strong>七、选型理由与保存</strong>
        </div>
        <el-input
          v-model="reason"
          type="textarea"
          :rows="3"
          :disabled="!canEdit"
          placeholder="留空时保存会自动生成"
        />
        <div class="save-bar">
          <span class="t-grey t-sm">
            <template v-if="saved">
              上次保存：{{ saved.updated_at ? saved.updated_at.slice(0, 19).replace('T', ' ') : '—' }}
              · {{ statusLabel }}
              <template v-if="saved.confirmed_by_name"> · 确认人 {{ saved.confirmed_by_name }}</template>
            </template>
            <template v-else>尚未保存</template>
          </span>
          <div>
            <el-button :disabled="!canEdit" :loading="saving" @click="persist('DRAFT')">保存草稿</el-button>
            <el-tooltip
              :disabled="hasSurveyBasis"
              content="没有勘察依据不能确认：请先录入勘察承载力表"
              placement="top"
            >
              <span>
                <el-button
                  type="primary"
                  :disabled="!canEdit || !hasSurveyBasis"
                  :loading="saving"
                  @click="persist('CONFIRMED')"
                >
                  确认方案
                </el-button>
              </span>
            </el-tooltip>
          </div>
        </div>
      </section>

      <!-- 八、桩基评估报告（TXT） -->
      <section class="app-card block">
        <div class="block-head">
          <strong>八、桩基评估报告</strong>
        </div>
        <div class="report-grid">
          <el-form-item label="报告标题">
            <el-input v-model="reportForm.report_title" placeholder="桩基评估" :disabled="!canEdit" />
          </el-form-item>
          <el-form-item label="报告日期">
            <el-input v-model="reportForm.date" placeholder="留空用今天" :disabled="!canEdit" />
          </el-form-item>
        </div>
        <el-form-item label="依据文件（一行一条，自动编号）">
          <el-input
            v-model="reportForm.basis_files"
            type="textarea"
            :rows="3"
            :disabled="!canEdit"
          />
        </el-form-item>
        <div class="report-actions">
          <el-button
            type="primary"
            :loading="reportBusy"
            :disabled="!canEdit || !saved"
            @click="generateReport"
          >
            生成 / 更新报告
          </el-button>
          <el-button :disabled="!reportText" @click="openReport(false)">预览 TXT</el-button>
          <el-button :disabled="!reportText" @click="openReport(true)">下载 TXT</el-button>
          <span v-if="saved && saved.report_generated_at" class="t-grey t-sm">
            上次生成：{{ saved.report_generated_at.slice(0, 19).replace('T', ' ') }}
          </span>
        </div>
        <el-input
          v-if="reportText"
          v-model="reportText"
          type="textarea"
          :rows="18"
          readonly
          class="report-preview"
        />
      </section>
    </template>

    <el-empty v-else description="还没有选型结论">
      <span class="t-grey t-sm">项目：{{ project?.name || '—' }}</span>
    </el-empty>
  </div>
</template>

<style scoped>
.page {
  max-width: 1680px;
}

.head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 18px;
  padding: 14px 20px;
  margin-bottom: 12px;
}
.head-l {
  min-width: 0;
}
.head-actions {
  display: flex;
  align-items: center;
  gap: 10px;
  flex: 0 0 auto;
}
.confirmed-hint {
  font-size: 12px;
}

.block {
  padding: 14px 18px;
  margin-bottom: 14px;
}
.block-head {
  display: flex;
  align-items: baseline;
  gap: 12px;
  margin-bottom: 12px;
}
.block-head strong {
  font-size: 15px;
}

/* ---------------- 条件 ---------------- */
.cond-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(230px, 1fr));
  gap: 8px;
}
.cond {
  border: 1px solid var(--line);
  border-radius: 6px;
  padding: 8px 10px;
  background: #fafcff;
}
.cond.hard {
  border-color: #f0d7a4;
  background: #fffdf7;
}
.cond.on {
  border-color: var(--blue);
  background: var(--blue-soft);
}
.num-grid {
  display: flex;
  flex-wrap: wrap;
  gap: 22px;
  margin-top: 14px;
}
.num-item {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 12.5px;
  color: var(--ink-2);
}
.num-item.scene {
  margin-left: auto;
}

.geo-collapse {
  margin-bottom: 14px;
  background: #fff;
  border: 1px solid var(--line);
  border-radius: 6px;
  padding: 4px 16px;
}

/* 依据提示：没有勘察数据时必须一眼看出来 */
.basis-alert {
  margin-bottom: 14px;
}

/* ---------------- 建议 / 校对 ---------------- */
.role-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 14px;
}
.role-card {
  border: 1px solid var(--line);
  border-radius: 6px;
  padding: 14px;
  background: #fafcff;
}
.role-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 10px;
}
.role-name {
  font-weight: 700;
  font-size: 14px;
  color: var(--ink);
}
.param-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px 14px;
  margin-top: 12px;
  font-size: 12.5px;
}
.param-grid span {
  color: var(--grey);
  margin-right: 8px;
}
.param-grid b {
  color: var(--ink);
}
.param-desc {
  margin-top: 10px;
  font-size: 12.5px;
  color: var(--ink-2);
  background: #fff;
  border: 1px dashed var(--line);
  border-radius: 4px;
  padding: 7px 10px;
}
.param-tags {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
  margin-top: 8px;
}
.manual-grid {
  display: grid;
  grid-template-columns: 1fr 1fr 1fr;
  gap: 8px;
  margin-top: 10px;
}
.opt-hint {
  float: right;
  color: #a8b3c2;
  font-size: 11.5px;
}

/* ---------------- 评分明细 ---------------- */
.rank-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 14px;
}
.rank-card {
  border: 1px solid var(--line);
  border-radius: 6px;
  overflow: hidden;
}
.rank-title {
  padding: 7px 12px;
  background: #f5f8fc;
  font-size: 12.5px;
  font-weight: 700;
  color: var(--ink-2);
}
.rank-row {
  display: grid;
  grid-template-columns: 26px minmax(0, 1.4fr) 88px minmax(0, 1fr);
  align-items: center;
  gap: 8px;
  padding: 7px 12px;
  border-top: 1px dashed var(--line);
  font-size: 12.5px;
}
.idx {
  color: #a8b3c2;
  font-family: Consolas, monospace;
  font-size: 11px;
}
.name {
  color: var(--ink);
}
.name.dim {
  color: #a8b3c2;
  text-decoration: line-through;
}
.cat {
  color: var(--grey);
  font-size: 11.5px;
}
.score {
  color: var(--blue);
}
.reason {
  color: var(--amber);
  font-size: 11.5px;
  line-height: 1.4;
}

/* ---------------- 保存 ---------------- */
.save-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 14px;
  margin-top: 14px;
}

/* ---------------- 建筑概况 / 非主楼数据表单 ---------------- */
.form-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
  gap: 6px 16px;
}
.form-grid :deep(.el-form-item) {
  margin-bottom: 8px;
}

/* ---------------- 报告 ---------------- */
.report-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 6px 16px;
}
.report-actions {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  margin: 4px 0 12px;
}
.report-preview :deep(.el-textarea__inner) {
  font-family: Consolas, 'Courier New', 'Microsoft YaHei', monospace;
  font-size: 12px;
  line-height: 1.7;
  background: #fafcff;
}

.skeleton {
  margin-top: 16px;
}

@media (max-width: 1100px) {
  .role-grid,
  .rank-grid {
    grid-template-columns: 1fr;
  }
}
@media (max-width: 720px) {
  .head {
    flex-direction: column;
  }
  .save-bar {
    flex-direction: column;
    align-items: flex-start;
  }
}
</style>
