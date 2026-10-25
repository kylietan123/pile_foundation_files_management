<script setup lang="ts">
/**
 * 合并版工作台。
 *
 * 顶部保留 hxr 风格的项目汇总；“我的项目”下面只保留项目名称，
 * 降低工作台的信息密度。点进项目后仍进入 oyx 版 7 阶段业务页。
 */
import { computed, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'

import { projectApi } from '@/api'
import { explainApiError } from '@/api/http'
import type { ProjectCreateIn } from '@/api/types'
import { useAuthStore } from '@/stores/auth'
import { useProjectStore } from '@/stores/project'

const router = useRouter()
const projectStore = useProjectStore()
const auth = useAuthStore()

const search = ref('')
const dialogVisible = ref(false)
const saving = ref(false)

const blankForm = (): ProjectCreateIn => ({
  name: '',
  short_name: '',
  location: '',
  province: '',
  city: '',
  project_type: '',
  scale_desc: '',
  description: '',
})
const form = reactive<ProjectCreateIn>(blankForm())

onMounted(() => {
  projectStore.fetchMyProjects()
})

const sum = computed(() => projectStore.summary())

const donutStyle = computed(() => {
  const total = Math.max(sum.value.total, 1)
  const inProgress = (sum.value.inProgress / total) * 100
  const archivedEnd = Math.min(inProgress + (sum.value.archived / total) * 100, 100)
  return {
    background: `conic-gradient(#1a6bb0 0 ${inProgress}%, #0ea5a4 ${inProgress}% ${archivedEnd}%, #d9e1ea ${archivedEnd}% 100%)`,
  }
})

const projects = computed(() => {
  const key = search.value.trim().toLowerCase()
  if (!key) return projectStore.projects
  return projectStore.projects.filter((p) =>
    [p.name, p.project_no, p.city, p.project_type].some((x) => x?.toLowerCase().includes(key)),
  )
})

function openProject(projectId: string) {
  router.push({ name: 'project-detail', params: { id: projectId } })
}

function openCreate() {
  Object.assign(form, blankForm())
  dialogVisible.value = true
}

async function submitProject() {
  if (!form.name?.trim()) {
    ElMessage.warning('请填写项目名称')
    return
  }
  saving.value = true
  try {
    const created = await projectApi.create({
      ...form,
      name: form.name.trim(),
      short_name: form.short_name?.trim() || form.name.trim(),
    })
    ElMessage.success('项目已创建，已建立 7 个阶段')
    await projectStore.fetchMyProjects()
    dialogVisible.value = false
    router.push({ name: 'project-detail', params: { id: created.id } })
  } catch (e) {
    ElMessage.error(explainApiError(e))
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <div class="workbench">
    <header class="workbench-head">
      <div>
        <div class="eyebrow">PROJECT WORKBENCH</div>
        <h2>工作台</h2>
        <p class="muted">
          {{ auth.user?.name }}，欢迎回来。管理你参与的项目与全过程工程文档。
        </p>
      </div>
      <el-button type="primary" size="large" @click="openCreate">
        <el-icon><Plus /></el-icon>
        新建项目
      </el-button>
    </header>

    <section class="overview-panel">
      <div class="overview-chart-wrap">
        <div class="overview-copy">
          <div class="overview-label">PROJECT OVERVIEW</div>
          <h3>项目概览</h3>
          <p>按你当前权限范围内的项目统计</p>
        </div>
        <div class="donut" :style="donutStyle">
          <div class="donut-center">
            <b>{{ sum.total }}</b>
            <span>参与项目</span>
          </div>
        </div>
        <div class="chart-legend">
          <span><i class="dot progress"></i>进行中 {{ sum.inProgress }}</span>
          <span><i class="dot archived"></i>已归档 {{ sum.archived }}</span>
          <span><i class="dot other"></i>其他 {{ Math.max(sum.total - sum.inProgress - sum.archived, 0) }}</span>
        </div>
      </div>

      <div class="overview-kpis">
        <div>
          <span>参与项目</span>
          <b>{{ sum.total }}</b>
        </div>
        <div>
          <span>进行中</span>
          <b>{{ sum.inProgress }}</b>
        </div>
        <div>
          <span>待我处理</span>
          <b>{{ sum.pendingTasks }}</b>
        </div>
        <div>
          <span>风险提醒</span>
          <b>{{ sum.overdue + sum.openIssues }}</b>
        </div>
      </div>
    </section>

    <section class="toolbar app-card">
      <div>
        <strong>我的项目</strong>
        <span class="muted">点击项目名称进入项目</span>
      </div>
      <el-input v-model="search" clearable placeholder="搜索项目" class="search">
        <template #prefix><el-icon><Search /></el-icon></template>
      </el-input>
    </section>

    <el-skeleton v-if="projectStore.loading" :rows="6" animated class="skeleton" />
    <el-alert
      v-else-if="projectStore.error"
      :title="projectStore.error"
      type="error"
      show-icon
      :closable="false"
    />

    <div v-else-if="projects.length" class="project-grid">
      <article
        v-for="p in projects"
        :key="p.id"
        class="project-card"
        @click="openProject(p.id)"
      >
        <div class="project-info">
          <div class="project-code">{{ p.project_no }}</div>
          <h3>{{ p.name }}</h3>
          <div class="project-location">{{ p.location || p.city || '地区未填写' }}</div>
        </div>
        <span class="enter-project">进入项目 →</span>
      </article>
    </div>

    <el-empty v-else description="没有匹配的项目">
      <el-button type="primary" @click="openCreate">创建第一个项目</el-button>
    </el-empty>

    <el-dialog v-model="dialogVisible" title="新建项目" width="560px" destroy-on-close>
      <el-form label-position="top" :model="form">
        <div class="form-grid">
          <el-form-item label="项目名称 *" class="span-2">
            <el-input v-model="form.name" placeholder="例如：杭州某商业综合体桩基工程" />
          </el-form-item>
          <el-form-item label="项目简称">
            <el-input v-model="form.short_name" placeholder="例如：杭州商业综合体" />
          </el-form-item>
          <el-form-item label="项目类型">
            <el-input v-model="form.project_type" placeholder="商业综合体 / 住宅 / 超高层" />
          </el-form-item>
          <el-form-item label="省份">
            <el-input v-model="form.province" placeholder="浙江省" />
          </el-form-item>
          <el-form-item label="城市">
            <el-input v-model="form.city" placeholder="杭州市" />
          </el-form-item>
          <el-form-item label="项目地点" class="span-2">
            <el-input v-model="form.location" placeholder="杭州市拱墅区" />
          </el-form-item>
          <el-form-item label="桩基规模" class="span-2">
            <el-input v-model="form.scale_desc" placeholder="例如：桩数 860 根，钻孔灌注桩为主" />
          </el-form-item>
          <el-form-item label="项目说明" class="span-2">
            <el-input v-model="form.description" type="textarea" :rows="3" />
          </el-form-item>
        </div>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="submitProject">
          创建并进入项目
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.workbench {
  max-width: 1460px;
  margin: 0 auto;
}

.workbench-head {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 20px;
  margin-bottom: 18px;
}

.eyebrow {
  color: #1a6bb0;
  font-size: 11px;
  font-weight: 800;
  letter-spacing: 2px;
}

.workbench-head h2 {
  margin: 2px 0;
  color: #1f2a3d;
  font-size: 26px;
}

.workbench-head p {
  margin: 0;
  font-size: 13px;
}

.overview-panel {
  display: grid;
  grid-template-columns: minmax(430px, 1fr) 1.1fr;
  align-items: center;
  gap: 22px;
  padding: 18px 22px;
  border: 1px solid #dce9f5;
  border-radius: 12px;
  background: linear-gradient(135deg, #f4f9ff 0%, #edf8f7 100%);
}

.overview-chart-wrap {
  display: grid;
  grid-template-columns: minmax(150px, 1fr) 94px 112px;
  align-items: center;
  gap: 16px;
}

.overview-label {
  color: #1a6bb0;
  font-size: 10.5px;
  font-weight: 800;
  letter-spacing: 1.6px;
}

.overview-copy h3 {
  margin: 3px 0 4px;
  color: #1f2a3d;
  font-size: 19px;
}

.overview-copy p {
  margin: 0;
  color: #6b7688;
  font-size: 12px;
}

.donut {
  width: 92px;
  height: 92px;
  padding: 10px;
  border-radius: 50%;
}

.donut-center {
  width: 100%;
  height: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  background: #fff;
}

.donut-center b {
  color: #1f2a3d;
  font-size: 21px;
  line-height: 1.1;
}

.donut-center span {
  margin-top: 2px;
  color: #8793a5;
  font-size: 10px;
}

.chart-legend {
  display: grid;
  gap: 7px;
  color: #536277;
  font-size: 11.5px;
}

.chart-legend span {
  display: flex;
  align-items: center;
  gap: 6px;
  white-space: nowrap;
}

.dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
}

.dot.progress {
  background: #1a6bb0;
}

.dot.archived {
  background: #0ea5a4;
}

.dot.other {
  background: #d9e1ea;
}

.overview-kpis {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  align-items: center;
}

.overview-kpis > div {
  padding: 4px 12px;
  border-left: 1px solid #d9e6f0;
}

.overview-kpis > div:first-child {
  border-left: none;
  padding-left: 0;
}

.overview-kpis span {
  display: block;
  color: #6b7688;
  font-size: 11.5px;
}

.overview-kpis b {
  display: block;
  margin-top: 4px;
  color: #1f2a3d;
  font-size: 23px;
  line-height: 1.1;
}

.toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 18px;
  margin: 16px 0;
  padding: 13px 16px;
}

.toolbar strong {
  margin-right: 12px;
  font-size: 15px;
}

.toolbar span {
  font-size: 12.5px;
}

.search {
  width: 260px;
}

.skeleton {
  margin-top: 16px;
}

.project-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 16px;
}

.project-card {
  position: relative;
  min-height: 168px;
  display: flex;
  align-items: flex-start;
  padding: 22px 22px 54px;
  border: 1px solid #dde4ec;
  border-radius: 10px;
  background: #fff;
  box-shadow: 0 3px 12px rgba(30, 50, 80, 0.05);
  cursor: pointer;
  transition: 0.18s ease;
}

.project-card:hover {
  transform: translateY(-2px);
  border-color: #1a6bb0;
  box-shadow: 0 9px 22px rgba(26, 107, 176, 0.14);
}

.project-info {
  min-width: 0;
}

.project-code {
  margin-bottom: 8px;
  color: #8793a5;
  font-family: Consolas, 'Courier New', monospace;
  font-size: 11.5px;
  font-weight: 600;
}

.project-card h3 {
  margin: 0;
  color: #1f2a3d;
  font-size: 16px;
  line-height: 1.5;
}

.project-location {
  margin-top: 10px;
  color: #6b7688;
  font-size: 12.5px;
}

.enter-project {
  position: absolute;
  right: 18px;
  bottom: 14px;
  color: #1a6bb0;
  font-size: 12px;
  font-weight: 600;
}

.form-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  column-gap: 14px;
}

.span-2 {
  grid-column: 1 / -1;
}

@media (max-width: 1100px) {
  .overview-panel {
    grid-template-columns: 1fr;
  }
  .project-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 720px) {
  .workbench-head {
    align-items: flex-start;
    flex-direction: column;
  }
  .toolbar {
    align-items: stretch;
    flex-direction: column;
  }
  .search {
    width: 100%;
  }
  .project-grid {
    grid-template-columns: 1fr;
  }
  .overview-chart-wrap {
    grid-template-columns: 1fr 82px;
  }
  .chart-legend {
    grid-column: 1 / -1;
    grid-template-columns: repeat(3, auto);
  }
  .overview-kpis {
    grid-template-columns: repeat(2, minmax(0, 1fr));
    row-gap: 16px;
  }
  .overview-kpis > div:nth-child(3) {
    border-left: none;
    padding-left: 0;
  }
  .form-grid {
    grid-template-columns: 1fr;
  }
  .span-2 {
    grid-column: auto;
  }
}
</style>
