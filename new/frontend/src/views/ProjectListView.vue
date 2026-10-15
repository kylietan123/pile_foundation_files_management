<script setup lang="ts">
/**
 * 合并版工作台。
 *
 * 外层采用 hxr 版的项目卡片工作台：欢迎语、汇总卡片、项目网格、新建项目。
 * 点进项目后仍进入 oyx 版项目详情与 7 阶段业务页。
 */
import { computed, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'

import { projectApi } from '@/api'
import { explainApiError } from '@/api/http'
import type { ProjectCreateIn, ProjectInfo } from '@/api/types'
import { PROJECT_STATUS_LABEL, STAGE_LABEL, UNIT_LABEL } from '@/api/types'
import StageRail from '@/components/StageRail.vue'
import { useAuthStore } from '@/stores/auth'
import { useProjectStore } from '@/stores/project'
import { formatDate } from '@/utils/format'

const router = useRouter()
const projectStore = useProjectStore()
const auth = useAuthStore()

const search = ref('')
const dialogVisible = ref(false)
const saving = ref(false)
const editingId = ref<string | null>(null)

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

const projects = computed(() => {
  const key = search.value.trim().toLowerCase()
  if (!key) return projectStore.projects
  return projectStore.projects.filter((p) =>
    [p.name, p.project_no, p.city, p.project_type].some((x) => x?.toLowerCase().includes(key)),
  )
})

function openProject(project: ProjectInfo) {
  router.push({ name: 'project-detail', params: { id: project.id } })
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

function isMine(project: ProjectInfo) {
  return project.my_primary_stages.length > 0 || auth.user?.is_superuser
}

function openCreate() {
  editingId.value = null
  Object.assign(form, blankForm())
  dialogVisible.value = true
}

function openEdit(project: ProjectInfo, event?: Event) {
  event?.stopPropagation()
  editingId.value = project.id
  Object.assign(form, {
    name: project.name,
    short_name: project.short_name || project.name,
    location: project.location || '',
    province: project.province || '',
    city: project.city || '',
    project_type: project.project_type || '',
    scale_desc: project.scale_desc || '',
    description: '',
  })
  dialogVisible.value = true
}

async function submitProject() {
  if (!form.name?.trim()) {
    ElMessage.warning('请填写项目名称')
    return
  }
  saving.value = true
  try {
    if (editingId.value) {
      await projectApi.update(editingId.value, {
        ...form,
        name: form.name.trim(),
        short_name: form.short_name?.trim() || form.name.trim(),
      })
      ElMessage.success('项目信息已保存')
      await projectStore.fetchMyProjects()
    } else {
      const created = await projectApi.create({
        ...form,
        name: form.name.trim(),
        short_name: form.short_name?.trim() || form.name.trim(),
      })
      ElMessage.success('项目已创建，已建立 7 个阶段')
      await projectStore.fetchMyProjects()
      dialogVisible.value = false
      router.push({ name: 'project-detail', params: { id: created.id } })
      return
    }
    dialogVisible.value = false
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

    <section class="stats">
      <div class="stat-card">
        <span>参与项目</span>
        <b>{{ sum.total }}</b>
        <small>仅显示权限范围内项目</small>
      </div>
      <div class="stat-card blue">
        <span>进行中</span>
        <b>{{ sum.inProgress }}</b>
        <small>含当前阶段推进项目</small>
      </div>
      <div class="stat-card amber">
        <span>待我处理</span>
        <b>{{ sum.pendingTasks }}</b>
        <small>跨项目工作流待办</small>
      </div>
      <div class="stat-card red">
        <span>风险提醒</span>
        <b>{{ sum.overdue + sum.openIssues }}</b>
        <small>逾期 {{ sum.overdue }} · 问题 {{ sum.openIssues }}</small>
      </div>
    </section>

    <section class="toolbar app-card">
      <div>
        <strong>我的项目</strong>
        <span class="muted">点击项目卡片进入 7 阶段协同空间</span>
      </div>
      <el-input v-model="search" clearable placeholder="搜索项目名称、编号或城市" class="search">
        <template #prefix><el-icon><Search /></el-icon></template>
      </el-input>
    </section>

    <el-skeleton v-if="projectStore.loading" :rows="8" animated class="skeleton" />
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
        @click="openProject(p)"
      >
        <div class="card-top">
          <div class="project-code">{{ p.project_no }}</div>
          <el-tag :type="statusTagType(p.status)" size="small" effect="light">
            {{ PROJECT_STATUS_LABEL[p.status] }}
          </el-tag>
        </div>

        <h3>{{ p.name }}</h3>
        <p class="meta">
          <span v-if="p.city || p.location">{{ p.city || p.location }}</span>
          <span v-if="p.project_type">{{ p.project_type }}</span>
          <span v-if="p.scale_desc">{{ p.scale_desc }}</span>
          <span v-if="!p.city && !p.project_type && !p.scale_desc">桩基工程全过程管理项目</span>
        </p>

        <div class="stage-line">
          <div class="stage-line-head">
            <span>当前阶段</span>
            <b>{{ STAGE_LABEL[p.current_stage_code] }}</b>
          </div>
          <StageRail :current="p.current_stage_code" />
        </div>

        <div class="card-metrics">
          <div>
            <span>待办</span>
            <b :class="{ alert: p.pending_task_count > 0 }">{{ p.pending_task_count }}</b>
          </div>
          <div>
            <span>逾期</span>
            <b :class="{ danger: p.overdue_count > 0 }">{{ p.overdue_count }}</b>
          </div>
          <div>
            <span>未闭环</span>
            <b :class="{ danger: p.open_issue_count > 0 }">{{ p.open_issue_count }}</b>
          </div>
        </div>

        <div class="card-foot">
          <div class="identity">
            <el-tag size="small" :type="isMine(p) ? 'warning' : 'info'" effect="plain">
              {{ p.my_unit_label || (p.my_unit ? UNIT_LABEL[p.my_unit] : '项目成员') }}
              <template v-if="p.my_responsibility_label"> · {{ p.my_responsibility_label }}</template>
            </el-tag>
            <span v-if="p.plan_end" class="muted">计划至 {{ formatDate(p.plan_end) }}</span>
          </div>
          <div class="actions">
            <el-button v-if="p.id && (p.my_primary_stages.length || auth.user?.is_superuser)" link @click="openEdit(p, $event)">
              编辑
            </el-button>
            <el-button type="primary" link @click.stop="openProject(p)">进入项目 →</el-button>
          </div>
        </div>
      </article>
    </div>

    <el-empty v-else description="没有匹配的项目">
      <el-button type="primary" @click="openCreate">创建第一个项目</el-button>
    </el-empty>

    <el-dialog
      v-model="dialogVisible"
      :title="editingId ? '编辑项目' : '新建项目'"
      width="560px"
      destroy-on-close
    >
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
          {{ editingId ? '保存' : '创建并进入项目' }}
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

.stats {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 13px;
}

.stat-card {
  padding: 15px 17px;
  border: 1px solid #dde4ec;
  border-radius: 10px;
  background: #fff;
  box-shadow: 0 3px 12px rgba(30, 50, 80, 0.04);
}

.stat-card span,
.stat-card small {
  display: block;
  color: #6b7688;
  font-size: 12px;
}

.stat-card b {
  display: block;
  margin: 3px 0;
  color: #1f2a3d;
  font-size: 25px;
  line-height: 1.2;
}

.stat-card.blue {
  border-top: 3px solid #1a6bb0;
}
.stat-card.amber {
  border-top: 3px solid #c8811a;
}
.stat-card.red {
  border-top: 3px solid #cf3b3b;
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
  width: 320px;
}

.skeleton {
  margin-top: 16px;
}

.project-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(350px, 1fr));
  gap: 16px;
}

.project-card {
  position: relative;
  padding: 18px;
  border: 1px solid #dde4ec;
  border-radius: 11px;
  background: #fff;
  box-shadow: 0 4px 16px rgba(30, 50, 80, 0.06);
  cursor: pointer;
  transition: 0.18s ease;
}

.project-card:hover {
  transform: translateY(-3px);
  border-color: #1a6bb0;
  box-shadow: 0 12px 28px rgba(26, 107, 176, 0.15);
}

.card-top,
.card-foot,
.stage-line-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.project-code {
  color: #1a6bb0;
  font-family: Consolas, 'Courier New', monospace;
  font-size: 11.5px;
  font-weight: 700;
}

.project-card h3 {
  margin: 12px 0 6px;
  color: #1f2a3d;
  font-size: 17px;
  line-height: 1.45;
}

.meta {
  display: flex;
  flex-wrap: wrap;
  gap: 5px 12px;
  min-height: 39px;
  margin: 0;
  color: #6b7688;
  font-size: 12.5px;
}

.meta span:not(:first-child)::before {
  content: '·';
  margin-right: 7px;
  color: #b6c0ce;
}

.stage-line {
  margin: 14px -2px 11px;
  padding: 12px 11px 8px;
  border-radius: 8px;
  background: #f6f9fc;
}

.stage-line-head {
  margin-bottom: 1px;
  color: #6b7688;
  font-size: 11.5px;
}

.stage-line-head b {
  color: #1a6bb0;
  font-size: 12px;
}

.project-card :deep(.stage-rail-mini) {
  margin: 10px 0 4px;
}

.project-card :deep(.stage-rail-mini .node) {
  font-size: 9.5px;
}

.card-metrics {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  margin: 12px 0;
  border: 1px solid #edf1f6;
  border-radius: 7px;
  overflow: hidden;
}

.card-metrics div {
  padding: 7px 10px;
  border-right: 1px solid #edf1f6;
}

.card-metrics div:last-child {
  border-right: 0;
}

.card-metrics span {
  display: block;
  color: #8793a5;
  font-size: 10.5px;
}

.card-metrics b {
  color: #4d5b6f;
  font-size: 16px;
}

.card-metrics b.alert {
  color: #1a6bb0;
}
.card-metrics b.danger {
  color: #cf3b3b;
}

.card-foot {
  padding-top: 11px;
  border-top: 1px dashed #e7edf4;
}

.identity {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.identity span {
  font-size: 11.5px;
  white-space: nowrap;
}

.actions {
  flex: 0 0 auto;
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
  .stats {
    grid-template-columns: repeat(2, 1fr);
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
  .stats {
    grid-template-columns: 1fr 1fr;
  }
  .card-foot {
    align-items: flex-start;
    flex-direction: column;
  }
  .form-grid {
    grid-template-columns: 1fr;
  }
  .span-2 {
    grid-column: auto;
  }
}
</style>
