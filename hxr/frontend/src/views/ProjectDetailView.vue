<script setup lang="ts">
/**
 * 项目总览：7 个阶段作为项目内导航。
 *
 * 这里是"7 个阶段"在界面上的正确位置 —— **项目内**，不是平台首页。
 * 点的每个阶段都是同一个项目的环节，共享同一套数据。
 *
 * 权限差异也在这里体现：
 *   有权限的阶段可点击进入；无权限的阶段显示为灰色不可点，
 *   并在底部说明原因。这样用户能自己搞明白"为什么我进不去"，
 *   而不是遇到一个莫名其妙的 403。
 */
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { catalogApi, projectApi } from '@/api'
import { explainApiError } from '@/api/http'
import type { CatalogDocument, ProjectMemberInfo } from '@/api/types'
import { PROJECT_STATUS_LABEL, STAGE_LABEL, STAGE_ORDER, UNIT_LABEL } from '@/api/types'
import type { UnitCode } from '@/api/types'
import { useAuthStore } from '@/stores/auth'
import { useProjectStore } from '@/stores/project'
import { formatDate } from '@/utils/format'

const route = useRoute()
const router = useRouter()
const projectStore = useProjectStore()
const auth = useAuthStore()

const projectId = computed(() => route.params.id as string)
const members = ref<ProjectMemberInfo[]>([])
const membersError = ref<string | null>(null)
const catalog = ref<CatalogDocument[]>([])
const catalogError = ref<string | null>(null)

onMounted(async () => {
  await projectStore.fetchDetail(projectId.value)
  try {
    members.value = await projectApi.members(projectId.value)
  } catch (e) {
    membersError.value = explainApiError(e)
  }
  try {
    catalog.value = await catalogApi.documents()
  } catch (e) {
    catalogError.value = explainApiError(e)
  }
})

const p = computed(() => projectStore.current)

const currentCatalog = computed(() => {
  const code = p.value?.current_stage_code
  return code ? catalog.value.filter((item) => item.stage_code === code) : []
})

const currentCatalogByUnit = computed(() => {
  const groups = new Map<string, CatalogDocument[]>()
  for (const item of currentCatalog.value) {
    const list = groups.get(item.responsible_unit_name) || []
    list.push(item)
    groups.set(item.responsible_unit_name, list)
  }
  return Array.from(groups.entries()).map(([unit, items]) => ({ unit, items }))
})

/** 我在此项目的成员关系 */
const myMembership = computed(() => auth.membershipOf(projectId.value))

/** 我是否有权进入某阶段 —— 阶段范围由《管理流程》矩阵推导，后端下发 */
function canEnterStage(code: string): boolean {
  if (auth.user?.is_superuser) return true
  return myMembership.value?.stages.includes(code as never) ?? false
}

/** 我是不是某阶段的主办单位 —— 主办阶段能上传、提交、发布 */
function isPrimaryOfStage(code: string): boolean {
  if (auth.user?.is_superuser) return true
  return myMembership.value?.primary_stages.includes(code as never) ?? false
}

/** 阶段显示状态 */
function stageState(code: string) {
  const stage = p.value?.stages.find((s) => s.stage_code === code)
  if (!stage) return { status: 'NOT_STARTED', progress: 0 }
  return { status: stage.status, progress: stage.progress }
}

/** 权限提示文案 —— 说明我在这个项目以什么单位参与、负责哪些阶段 */
const permHint = computed(() => {
  const m = myMembership.value
  if (!m) {
    return {
      type: 'error' as const,
      text: '你不是该项目的参与单位成员，请联系项目管理员把你的单位加入项目。',
    }
  }
  const covered = m.stages
  const denied = STAGE_ORDER.filter((s) => !covered.includes(s)).map((s) => STAGE_LABEL[s])
  const primary = m.primary_stages.map((s) => STAGE_LABEL[s])
  const text =
    `你以「${m.unit_label}」参与本项目，责任等级：${m.responsibility_label || '参与'}。` +
    (primary.length ? `你是「${primary.join('、')}」阶段的主办单位，可以上传与发布。` : '') +
    `可见阶段：${covered.map((s) => STAGE_LABEL[s]).join('、') || '无'}。` +
    (denied.length ? `因此对「${denied.join('、')}」看不到入口。` : '') +
    `换成其他项目，同一套菜单会自动变化 —— 不需要为 7 个阶段各配一遍权限。`
  return { type: 'warning' as const, text }
})

function enterStage(code: string) {
  if (!canEnterStage(code)) return
  // 阶段优先：点阶段直接进入该阶段的「文件与版本」工作区，
  // 顶部有 StageContextBar 可切本阶段的其他功能（变更/问题/成果/台账）。
  router.push({ name: 'documents', params: { id: projectId.value }, query: { stage: code } })
}

/**
 * 近期动态 —— 由真实项目数据推导，不写死。
 * 后续接入 audit_log 接口后改为后端返回，这里的结构可以直接替换。
 */
const activity = computed(() => {
  const proj = p.value
  if (!proj) return []
  const items: { time: string; text: string; who: string; warn?: string }[] = []

  // 已经完成的阶段 → 完成记录
  const completed = proj.stages.filter((s) => s.status === 'COMPLETED' && s.actual_end)
  for (const s of completed.slice(-3)) {
    items.push({
      time: formatDate(s.actual_end),
      text: `${STAGE_LABEL[s.stage_code]}阶段已完成`,
      who: '系统',
    })
  }

  // 当前阶段 → 进展
  const cur = proj.stages.find((s) => s.stage_code === proj.current_stage_code)
  if (cur) {
    items.push({
      time: formatDate(cur.actual_start || proj.actual_start),
      text: `${STAGE_LABEL[cur.stage_code]}阶段进行中，完成 ${cur.progress}%`,
      who: '系统',
    })
  }

  // 未闭环问题 → 风险提示
  if (proj.open_issue_count > 0) {
    items.push({
      time: formatDate(new Date().toISOString()),
      text: `存在 ${proj.open_issue_count} 项未闭环问题`,
      who: '系统',
      warn: '→ 需处理后才能归档',
    })
  }

  return items.reverse().slice(0, 6)
})
</script>

<template>
  <div class="page">
    <el-skeleton v-if="projectStore.loading && !p" :rows="8" animated />

    <el-alert
      v-else-if="projectStore.error"
      :title="projectStore.error"
      type="error"
      show-icon
      :closable="false"
    />

    <template v-else-if="p">
      <!-- 项目条 -->
      <div class="projbar">
        <div>
          <div class="pname">{{ p.name }}</div>
          <div class="pcode">
            {{ p.project_no }}
            <template v-if="p.city"> · {{ p.city }}</template>
            <template v-if="p.scale_desc"> · {{ p.scale_desc }}</template>
          </div>
        </div>
        <div class="pright">
          <el-tag :type="p.status === 'IN_PROGRESS' ? 'primary' : 'info'" effect="dark" size="small">
            {{ PROJECT_STATUS_LABEL[p.status] }}
          </el-tag>
          <el-button
            v-if="p.current_stage_code === 'DESIGN' || canEnterStage('DESIGN')"
            size="small"
            plain
            @click="router.push({ name: 'design-inputs', params: { id: projectId } })"
          >
            设计输入管理
          </el-button>
          <el-button size="small" plain @click="router.push({ name: 'projects' })">
            切换项目
          </el-button>
        </div>
      </div>

      <!-- 一句话说明这个页面干什么 -->
      <div class="purpose">
        选择下方<b>阶段</b>进入工作区：上传 / 查看文件、发起变更、处理问题、查看台账。
      </div>

      <!-- 7 阶段导航 -->
      <div class="stages">
        <div
          v-for="(code, i) in STAGE_ORDER"
          :key="code"
          class="stage"
          :class="{
            done: stageState(code).status === 'COMPLETED',
            current: code === p.current_stage_code,
            locked: !canEnterStage(code),
            mine: isPrimaryOfStage(code),
          }"
          :title="
            !canEnterStage(code)
              ? '你的单位在此阶段没有责任'
              : isPrimaryOfStage(code)
                ? '你是本阶段主办单位，可上传与发布'
                : '你是本阶段相关单位，可查看与签认'
          "
          @click="enterStage(code)"
        >
          <div class="st-n">{{ String(i + 1).padStart(2, '0') }}</div>
          <div class="st-t">{{ STAGE_LABEL[code] }}</div>
          <div v-if="isPrimaryOfStage(code)" class="st-own">主办</div>
        </div>
      </div>

      <!-- 统计 -->
      <div class="stats">
        <div class="stat app-card">
          <div class="lab">当前阶段</div>
          <div class="val t-blue">{{ p.current_stage_label || STAGE_LABEL[p.current_stage_code] }}</div>
          <div class="sub">
            <template v-if="p.my_unit_label">
              我以「{{ p.my_unit_label }}」参与<template
                v-if="p.my_responsibility_label"
              >
                · {{ p.my_responsibility_label }}</template
              >
            </template>
            <template v-else>只读访问</template>
          </div>
        </div>
        <div class="stat app-card">
          <div class="lab">阶段进度</div>
          <div class="val t-blue">
            {{ stageState(p.current_stage_code).progress }}<span class="unit">%</span>
          </div>
          <div class="sub">
            计划 {{ formatDate(p.plan_start) }} ~ {{ formatDate(p.plan_end) }}
          </div>
        </div>
        <div class="stat app-card">
          <div class="lab">待我处理 / 逾期</div>
          <div class="val">
            <span class="t-blue">{{ p.pending_task_count }}</span>
            <span class="slash">/</span>
            <span :class="p.overdue_count > 0 ? 't-red' : 't-grey'">{{ p.overdue_count }}</span>
          </div>
          <div class="sub">逾期项请优先处理</div>
        </div>
        <div class="stat app-card">
          <div class="lab">未闭环问题</div>
          <div class="val" :class="p.open_issue_count > 0 ? 't-red' : ''">
            {{ p.open_issue_count }}
          </div>
          <div class="sub">全部闭环后方可归档</div>
        </div>
      </div>

      <!-- 权限说明 -->
      <div class="perm-note" :class="permHint.type">
        <b>权限如何生效：</b>{{ permHint.text }}
      </div>
    </template>
  </div>
</template>

<style scoped>
.page {
  max-width: 1680px;
}

/* ---------------- 项目条 ---------------- */
.projbar {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 14px 20px;
  background: linear-gradient(90deg, #12305c, #1c4a86);
  color: #fff;
  border-radius: 6px 6px 0 0;
}
.pname {
  font-size: 17px;
  font-weight: 700;
}
.pcode {
  font-size: 12.5px;
  color: #a9c6e6;
  margin-top: 2px;
}
.pright {
  margin-left: auto;
  display: flex;
  align-items: center;
  gap: 10px;
}

/* 一句话说明本页用途 */
.purpose {
  font-size: 13px;
  color: #6b7688;
  background: #fff;
  border: 1px solid var(--line);
  border-radius: 6px;
  padding: 10px 16px;
  margin-top: 12px;
}
.purpose b {
  color: var(--blue);
  font-weight: 700;
}

/* ---------------- 7 阶段导航 ---------------- */
.stages {
  display: flex;
  background: #fff;
  border: 1px solid var(--line);
  border-top: none;
  border-radius: 0 0 6px 6px;
  overflow: hidden;
}
.stage {
  flex: 1;
  padding: 12px 6px 11px;
  text-align: center;
  font-size: 13.5px;
  color: var(--grey);
  cursor: pointer;
  border-bottom: 3px solid transparent;
  border-right: 1px solid #f0f3f8;
  position: relative;
  transition: background 0.15s;
  user-select: none;
}
.stage:last-child {
  border-right: none;
}
.stage:hover:not(.locked) {
  background: #f7f9fc;
}
.st-n {
  font-size: 11px;
  color: #a8b4c2;
  letter-spacing: 0.5px;
}
.st-t {
  margin-top: 1px;
}
.stage.done {
  color: var(--teal);
}
.stage.done .st-n {
  color: #5cc0b5;
}
.stage.done::after {
  content: '✓';
  font-size: 11px;
  margin-left: 5px;
}
.stage.current {
  color: var(--blue);
  font-weight: 700;
  border-bottom-color: var(--blue);
  background: var(--blue-soft);
}
.stage.current .st-n {
  color: #5b96e0;
}
/* 我是主办单位的阶段 —— 能上传与发布 */
.stage .st-own {
  position: absolute;
  top: 3px;
  right: 5px;
  font-size: 9.5px;
  background: var(--red);
  color: #fff;
  padding: 1px 5px;
  border-radius: 2px;
  font-weight: 700;
}
/* 无权限的阶段 */
.stage.locked {
  color: #c3cbd6;
  cursor: not-allowed;
}
.stage.locked .st-n {
  color: #d5dbe3;
}
.stage.locked:hover {
  background: transparent;
}

/* ---------------- 参与单位的阶段标签 ---------------- */
.stg-cell {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}
.stg-chip {
  font-size: 11.5px;
  padding: 1px 7px;
  border-radius: 3px;
  background: #f1f4f8;
  color: var(--grey);
  border: 1px solid transparent;
}
/* 主办阶段：深色，一眼看出这个单位在哪个阶段管事 */
.stg-chip.own {
  background: var(--red-soft);
  color: #8a2f26;
  border-color: #f3c9c4;
  font-weight: 700;
}

/* ---------------- 统计 ---------------- */
.stats {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 14px;
  margin-top: 16px;
}
.stat {
  padding: 14px 16px;
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
  font-size: 14px;
  font-weight: 400;
}
.stat .val .slash {
  color: #cfd6de;
  margin: 0 4px;
  font-weight: 400;
}
.stat .sub {
  font-size: 12px;
  color: var(--grey);
  margin-top: 3px;
}

/* ---------------- 两列 ---------------- */
.two-col {
  display: grid;
  grid-template-columns: 1.35fr 1fr;
  gap: 16px;
  margin-top: 16px;
}
.pad {
  padding: 16px 18px;
}

.prog-row {
  display: flex;
  align-items: center;
  gap: 11px;
  padding: 9px 0;
  border-bottom: 1px dashed #eef2f7;
  font-size: 13px;
}
.prog-row:last-child {
  border-bottom: none;
}
.prog-row.hl {
  background: var(--blue-soft);
  margin: 0 -18px;
  padding: 9px 18px;
}
.prog-row .nm {
  width: 92px;
  color: var(--ink-2);
  white-space: nowrap;
}
.prog-row .nm.lock {
  color: #b7c0cb;
}
.bar {
  flex: 1;
  height: 8px;
  background: #eef1f5;
  border-radius: 4px;
  overflow: hidden;
}
.bar i {
  display: block;
  height: 100%;
  border-radius: 4px;
  transition: width 0.3s;
}
.prog-row .pv {
  width: 56px;
  text-align: right;
  font-weight: 700;
  font-size: 12.5px;
}

/* ---------------- 动态 ---------------- */
.act {
  display: flex;
  align-items: baseline;
  gap: 12px;
  padding: 8px 0;
  border-bottom: 1px dashed #eef2f7;
  font-size: 13px;
}
.act:last-child {
  border-bottom: none;
}
.act .at {
  flex: 0 0 96px;
}
.act .ax {
  flex: 1;
  color: var(--ink-2);
}
.act .aw {
  flex: 0 0 66px;
  text-align: right;
}

/* ---------------- 权限说明 ---------------- */
.perm-note {
  margin-top: 16px;
  border-radius: 6px;
  padding: 12px 16px;
  font-size: 12.5px;
  line-height: 1.8;
}
.perm-note.warning {
  background: #fffaf0;
  border: 1px solid #f0dcb0;
  color: #7a5a17;
}
.perm-note.error {
  background: var(--red-soft);
  border: 1px solid #f0c0c0;
  color: #8a2f2f;
}
.perm-note b {
  font-weight: 700;
}

.catalog-groups {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}
.catalog-group {
  border: 1px solid #e7edf4;
  border-radius: 6px;
  overflow: hidden;
}
.catalog-unit {
  display: flex;
  justify-content: space-between;
  padding: 8px 11px;
  background: #f7f9fc;
  color: #4a5866;
  font-size: 12.5px;
}
.catalog-unit span {
  color: #8793a5;
}
.catalog-items {
  max-height: 250px;
  overflow: auto;
}
.catalog-item {
  display: grid;
  grid-template-columns: 56px minmax(0, 1fr) auto;
  align-items: center;
  gap: 9px;
  padding: 8px 11px;
  border-top: 1px dashed #eef2f7;
  font-size: 12.5px;
}
.catalog-code {
  color: #1e6fd9;
  font-family: Consolas, 'Courier New', monospace;
  font-size: 11px;
}
.catalog-name {
  color: #37465a;
  line-height: 1.45;
}
@media (max-width: 1100px) {
  .catalog-groups {
    grid-template-columns: 1fr;
  }
}
</style>
