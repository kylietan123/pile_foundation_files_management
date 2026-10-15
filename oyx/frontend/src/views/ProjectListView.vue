<script setup lang="ts">
/**
 * 首页：我的项目。
 *
 * 为什么首页是项目列表而不是 7 个阶段板块？
 *   因为一个人会同时参与多个项目（已确认的实际情况）。
 *   如果按阶段分入口，进「设计」时还得再选一次项目，
 *   而且"待我处理 5"到底是哪个项目的数字说不清。
 *
 * 所以层级是：项目 → 阶段 → 业务功能。
 */
import { computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'

import type { ProjectInfo } from '@/api/types'
import { PROJECT_STATUS_LABEL, STAGE_LABEL, UNIT_LABEL } from '@/api/types'
import StageRail from '@/components/StageRail.vue'
import { useAuthStore } from '@/stores/auth'
import { useProjectStore } from '@/stores/project'

const router = useRouter()
const projectStore = useProjectStore()
const auth = useAuthStore()

onMounted(() => {
  projectStore.fetchMyProjects()
})

const sum = computed(() => projectStore.summary())

/** 跨项目待办与风险 —— 一人多项目场景下的刚需 */
const crossProject = computed(() => {
  const items: {
    projectName: string
    projectId: string
    stage: string
    pending: number
    overdue: number
    issues: number
    level: 'high' | 'mid' | 'low'
  }[] = []
  for (const p of projectStore.projects) {
    if (p.pending_task_count + p.overdue_count + p.open_issue_count === 0) continue
    const level: 'high' | 'mid' | 'low' =
      p.overdue_count > 0 ? 'high' : p.open_issue_count > 0 ? 'mid' : 'low'
    items.push({
      projectName: p.short_name || p.name,
      projectId: p.id,
      stage: STAGE_LABEL[p.current_stage_code] ?? p.current_stage_code,
      pending: p.pending_task_count,
      overdue: p.overdue_count,
      issues: p.open_issue_count,
      level,
    })
  }
  return items.sort((a, b) => {
    const rank = { high: 0, mid: 1, low: 2 }
    return rank[a.level] - rank[b.level] || b.overdue - a.overdue
  })
})

function openProject(p: ProjectInfo) {
  router.push({ name: 'project-detail', params: { id: p.id } })
}

function statusTagType(status: string): 'success' | 'info' | 'warning' | 'primary' | 'danger' {
  switch (status) {
    case 'IN_PROGRESS':
      return 'primary'
    case 'COMPLETED':
      return 'success'
    case 'ARCHIVED':
      return 'info'
    case 'SUSPENDED':
      return 'danger'
    default:
      return 'warning'
  }
}

// 我是不是这个项目的主办单位之一（有主办阶段就说明我在管事）
const isMine = (p: ProjectInfo) => p.my_primary_stages.length > 0
</script>

<template>
  <div class="page">
    <!-- 顶部汇总 -->
    <div class="head">
      <div>
        <h2>我的项目</h2>
        <p class="t-grey t-sm">
          {{ auth.user?.name }} · 参与 {{ sum.total }} 个项目 ·
          待办 {{ sum.pendingTasks }} 项<template v-if="sum.overdue">
            （<span class="t-red">逾期 {{ sum.overdue }}</span>）
          </template>
          · 未闭环问题 {{ sum.openIssues }} 项
        </p>
      </div>
      <div class="head-right">
        <el-button disabled>
          <el-icon><Plus /></el-icon>
          新建项目
        </el-button>
      </div>
    </div>

    <!-- 加载中 -->
    <el-skeleton v-if="projectStore.loading" :rows="6" animated />

    <!-- 错误 -->
    <el-alert
      v-else-if="projectStore.error"
      :title="projectStore.error"
      type="error"
      show-icon
      :closable="false"
    />

    <template v-else>
      <!-- 项目卡片 -->
      <div class="cards">
        <div
          v-for="p in projectStore.projects"
          :key="p.id"
          class="pcard app-card"
          :class="{ focus: p.id === projectStore.current?.id }"
          @click="openProject(p)"
        >
          <div class="pc-head">
            <div class="pc-l">
              <div class="pc-name">{{ p.name }}</div>
              <div class="pc-meta t-grey t-sm">
                {{ p.project_no }}
                <template v-if="p.city"> · {{ p.city }}</template>
                <template v-if="p.project_type"> · {{ p.project_type }}</template>
                <template v-if="p.scale_desc"> · {{ p.scale_desc }}</template>
              </div>
            </div>
            <div class="pc-r">
              <el-tag :type="statusTagType(p.status)" size="small" effect="light">
                {{ PROJECT_STATUS_LABEL[p.status] }}
              </el-tag>
              <el-tag
                v-if="p.my_unit"
                class="role-tag"
                size="small"
                effect="plain"
                :type="isMine(p) ? 'warning' : 'info'"
              >
                {{ p.my_unit_label || UNIT_LABEL[p.my_unit] }}
                <template v-if="p.my_responsibility_label">
                  · {{ p.my_responsibility_label }}
                </template>
              </el-tag>
            </div>
          </div>

          <StageRail :current="p.current_stage_code" />

          <div class="pc-foot">
            <span class="t-grey">待我处理</span>
            <b class="t-blue">{{ p.pending_task_count }}</b>
            <span class="sep">|</span>
            <span class="t-grey">逾期</span>
            <b :class="p.overdue_count > 0 ? 't-red' : ''">{{ p.overdue_count }}</b>
            <span class="sep">|</span>
            <span class="t-grey">未闭环问题</span>
            <b :class="p.open_issue_count > 0 ? 't-amber' : ''">{{ p.open_issue_count }}</b>
            <span class="enter">进入项目 →</span>
          </div>
        </div>
      </div>

      <!-- 跨项目视图 -->
      <div class="sec-title" style="margin-top: 26px">
        跨项目视图
        <span class="more">不进入项目也能看到压在自己手上的活</span>
      </div>

      <div class="app-card" style="overflow: hidden">
        <el-table
          :data="crossProject"
          style="width: 100%"
          :empty-text="'当前没有待办与风险，很干净'"
          @row-click="(row: any) => router.push({ name: 'project-detail', params: { id: row.projectId } })"
        >
          <el-table-column label="紧急度" width="110">
            <template #default="{ row }">
              <el-tag
                size="small"
                :type="row.level === 'high' ? 'danger' : row.level === 'mid' ? 'warning' : 'success'"
                effect="light"
              >
                {{ row.level === 'high' ? '高' : row.level === 'mid' ? '中' : '低' }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="projectName" label="项目" min-width="180" />
          <el-table-column label="当前阶段" width="120">
            <template #default="{ row }">{{ row.stage }}</template>
          </el-table-column>
          <el-table-column label="待我处理" width="110" align="center">
            <template #default="{ row }">
              <span class="t-blue"><b>{{ row.pending }}</b></span>
            </template>
          </el-table-column>
          <el-table-column label="逾期" width="90" align="center">
            <template #default="{ row }">
              <span :class="row.overdue > 0 ? 't-red' : 't-grey'">
                <b>{{ row.overdue }}</b>
              </span>
            </template>
          </el-table-column>
          <el-table-column label="未闭环问题" width="120" align="center">
            <template #default="{ row }">
              <span :class="row.issues > 0 ? 't-amber' : 't-grey'">
                <b>{{ row.issues }}</b>
              </span>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="100">
            <template #default>
              <span class="t-blue" style="cursor: pointer">进入</span>
            </template>
          </el-table-column>
        </el-table>
      </div>

      <!-- 权限说明 -->
      <div class="perm-note">
        <b>权限如何生效（一份配置，全局一致）：</b>
        权限挂在「<b>项目 + 参与单位</b>」上，不按 7 个阶段各配一遍 ——
        每个阶段的权限由《管理流程》责任矩阵自动推导。
        同一个人在不同项目可以是不同单位（例如欧雨欣在杭州项目是
        <b>设计单位</b>，在苏州项目是<b>勘察单位</b>），登录后菜单与可用操作自动变化。
        <br />
        项目列表由后端在 SQL 层按单位过滤 —— 你无权访问的项目根本不会返回。
      </div>
    </template>
  </div>
</template>

<style scoped>
.page {
  max-width: 1680px;
}

.head {
  display: flex;
  align-items: flex-start;
  margin-bottom: 18px;
}
.head h2 {
  margin: 0 0 4px;
  font-size: 19px;
  font-weight: 700;
}
.head-right {
  margin-left: auto;
}

/* ---------------- 项目卡片 ---------------- */
.cards {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(500px, 1fr));
  gap: 16px;
}

.pcard {
  padding: 16px 18px 14px;
  cursor: pointer;
  transition:
    border-color 0.15s,
    box-shadow 0.15s,
    transform 0.15s;
}
.pcard:hover {
  border-color: var(--blue);
  box-shadow: 0 4px 16px rgba(30, 111, 217, 0.13);
  transform: translateY(-1px);
}

.pc-head {
  display: flex;
  align-items: flex-start;
  gap: 12px;
}
.pc-l {
  min-width: 0;
}
.pc-name {
  font-size: 15.5px;
  font-weight: 700;
  color: var(--ink);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.pc-meta {
  margin-top: 3px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.pc-r {
  margin-left: auto;
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 6px;
  flex: 0 0 auto;
}
.role-tag {
  font-weight: 600;
}

.pc-foot {
  display: flex;
  align-items: center;
  gap: 7px;
  padding-top: 11px;
  border-top: 1px dashed var(--line);
  font-size: 12.5px;
}
.pc-foot .sep {
  color: #dfe5ec;
}
.pc-foot b {
  font-size: 13px;
}
.pc-foot .enter {
  margin-left: auto;
  color: var(--blue);
}

/* ---------------- 权限说明 ---------------- */
.perm-note {
  margin-top: 18px;
  background: #fffaf0;
  border: 1px solid #f0dcb0;
  border-radius: 6px;
  padding: 12px 16px;
  font-size: 12.5px;
  color: #7a5a17;
  line-height: 1.8;
}
.perm-note b {
  color: #8a5a00;
}
</style>
