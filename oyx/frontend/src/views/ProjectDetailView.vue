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

import { projectApi } from '@/api'
import { explainApiError } from '@/api/http'
import type { ProjectMemberInfo } from '@/api/types'
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

onMounted(async () => {
  await projectStore.fetchDetail(projectId.value)
  try {
    members.value = await projectApi.members(projectId.value)
  } catch (e) {
    membersError.value = explainApiError(e)
  }
})

const p = computed(() => projectStore.current)

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
  router.push({ name: 'project-detail', params: { id: projectId.value }, query: { stage: code } })
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
          <el-button size="small" plain @click="router.push({ name: 'projects' })">
            切换项目
          </el-button>
        </div>
      </div>

      <!-- 工作入口：当前阶段的可用功能。
           没有这段，点了「设计」阶段也不知道该去哪。 -->
      <div v-if="canEnterStage(p.current_stage_code)" class="entries app-card">
        <span class="el-label">进入工作：</span>
        <el-button
          v-if="p.current_stage_code === 'DESIGN' || canEnterStage('DESIGN')"
          size="small"
          type="primary"
          plain
          @click="router.push({ name: 'design-inputs', params: { id: projectId } })"
        >
          设计输入管理
        </el-button>
        <el-button
          size="small"
          plain
          @click="router.push({ name: 'documents', params: { id: projectId } })"
        >
          文件与版本
        </el-button>
        <el-button
          size="small"
          plain
          @click="router.push({ name: 'changes', params: { id: projectId } })"
        >
          设计变更
        </el-button>
        <el-button
          size="small"
          plain
          @click="router.push({ name: 'issues', params: { id: projectId } })"
        >
          问题管理
          <el-tag
            v-if="p.open_issue_count"
            size="small"
            type="danger"
            effect="dark"
            style="margin-left: 4px"
          >
            {{ p.open_issue_count }}
          </el-tag>
        </el-button>
        <el-button
          size="small"
          type="primary"
          plain
          @click="router.push({ name: 'deliverables', params: { id: projectId } })"
        >
          设计成果与交付
        </el-button>
        <el-button
          size="small"
          type="warning"
          plain
          @click="router.push({ name: 'ledger', params: { id: projectId } })"
        >
          文件台账与追溯
        </el-button>
        <el-button
          size="small"
          plain
          @click="router.push({ name: 'ai', query: { project: projectId } })"
        >
          AI 助手
        </el-button>
        <span class="el-hint t-grey">
          后续迭代补齐：设计参数库 / 桩型智能选型
        </span>
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

      <div class="two-col">
        <!-- 各阶段推进情况 -->
        <div class="app-card pad">
          <div class="sec-title">
            各阶段推进情况
            <span class="more" @click="enterStage(p.current_stage_code)">进入当前阶段</span>
          </div>
          <div v-for="s in p.stages" :key="s.id" class="prog-row" :class="{ hl: s.stage_code === p.current_stage_code }">
            <span class="nm" :class="{ lock: !canEnterStage(s.stage_code) }">
              {{ STAGE_LABEL[s.stage_code] }}
            </span>
            <div class="bar">
              <i
                :style="{
                  width: s.progress + '%',
                  background:
                    s.status === 'COMPLETED' ? 'var(--teal)' : s.status === 'IN_PROGRESS' ? 'var(--blue)' : '#dfe5ec',
                }"
              />
            </div>
            <span class="pv" :class="s.status === 'COMPLETED' ? 't-teal' : s.status === 'IN_PROGRESS' ? 't-blue' : 't-grey'">
              {{ s.status === 'NOT_STARTED' ? '未开始' : s.progress + '%' }}
            </span>
          </div>
        </div>

        <!-- 参与单位与阶段责任 -->
        <div class="app-card pad">
          <div class="sec-title">
            参与单位与阶段责任
            <span class="more">{{ members.length }} 条参与关系</span>
          </div>
          <el-alert
            v-if="membersError"
            :title="membersError"
            type="warning"
            :closable="false"
            show-icon
          />
          <el-table v-else :data="members" size="small" style="width: 100%">
            <el-table-column prop="user_name" label="姓名" width="90">
              <template #default="{ row }">
                <span>{{ row.user_name }}</span>
                <div v-if="row.employee_no" class="t-grey t-sm t-mono">
                  {{ row.employee_no }}
                </div>
              </template>
            </el-table-column>
            <el-table-column label="参与单位" width="150">
              <template #default="{ row }">
                <el-tag size="small" effect="plain">
                  {{ row.unit_label || UNIT_LABEL[row.unit_code as UnitCode] }}
                </el-tag>
                <div v-if="row.org_name" class="t-grey t-sm">{{ row.org_name }}</div>
              </template>
            </el-table-column>
            <el-table-column label="责任等级" width="100" align="center">
              <template #default="{ row }">
                <!-- 按**展示用责任等级**判断，不要用 primary_stages.length：
                     一个单位可能只在某个阶段是主办，但它在别的阶段也有责任，
                     用长度判断会把所有"有主办阶段"的单位都标成主办。 -->
                <el-tag
                  v-if="row.responsibility === 'PRIMARY'"
                  size="small"
                  type="danger"
                  effect="light"
                >
                  主办
                </el-tag>
                <el-tag
                  v-else-if="row.responsibility === 'RELATED'"
                  size="small"
                  type="warning"
                  effect="plain"
                >
                  相关
                </el-tag>
                <el-tag v-else size="small" type="info" effect="plain">参与</el-tag>
              </template>
            </el-table-column>
            <el-table-column label="负责阶段">
              <template #default="{ row }">
                <div class="stg-cell">
                  <span
                    v-for="c in row.stages || []"
                    :key="c"
                    class="stg-chip"
                    :class="{ own: (row.primary_stages || []).includes(c) }"
                  >
                    {{ STAGE_LABEL[c as never] || c }}
                  </span>
                </div>
              </template>
            </el-table-column>
          </el-table>
          <div class="t-grey t-sm" style="margin-top: 8px">
            责任等级由《管理流程》矩阵决定：<b class="t-red">深色</b>表示该单位在此阶段是主办（可上传/发布），
            浅色表示相关或参与（可查看，相关单位可签认）。
          </div>
        </div>
      </div>

      <!-- 近期动态 -->
      <div class="app-card pad" style="margin-top: 16px">
        <div class="sec-title">近期动态<span class="more">近 7 天</span></div>
        <div v-for="(a, i) in activity" :key="i" class="act">
          <span class="at t-grey t-mono t-sm">{{ a.time }}</span>
          <span class="ax">
            {{ a.text }}
            <span v-if="a.warn" class="t-red t-sm"> {{ a.warn }}</span>
          </span>
          <span class="aw t-grey t-sm">{{ a.who }}</span>
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

/* 工作入口条 */
.entries {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 11px 18px;
  margin-top: 12px;
  flex-wrap: wrap;
}
.entries .el-label {
  font-size: 13px;
  color: var(--grey);
}
.entries .el-hint {
  font-size: 12px;
  margin-left: 6px;
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
</style>
