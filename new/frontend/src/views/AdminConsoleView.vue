<script setup lang="ts">
/**
 * 系统 / 部门管理员控制台。
 *
 * 总管理员看全部单位；部门管理员只看本部门，只能在本部门创建账号，
 * 并把员工加入本部门已参与的项目、分配本部门有责任的阶段。
 * 它不是工作台；管理员需要查看项目时，通过顶部导航的工作台切换。
 */
import { computed, nextTick, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'

import { adminApi } from '@/api'
import { useAuthStore } from '@/stores/auth'
import { explainApiError } from '@/api/http'
import type {
  AdminBulkUserItem,
  AdminMembership,
  AdminOptions,
  AdminOverview,
  AdminPermissionAssignment,
  AdminUser,
  AdminUserCreateIn,
  Responsibility,
  StageCode,
  UnitCode,
} from '@/api/types'

const auth = useAuthStore()

const loading = ref(false)
const saving = ref(false)
const users = ref<AdminUser[]>([])
const options = ref<AdminOptions | null>(null)
const overview = ref<AdminOverview | null>(null)
const keyword = ref('')

const createVisible = ref(false)
const bulkCreateVisible = ref(false)
const permissionVisible = ref(false)
const resetVisible = ref(false)
const editVisible = ref(false)
const membershipVisible = ref(false)
const deactivateVisible = ref(false)
const bulkDeactivateVisible = ref(false)
const targetUser = ref<AdminUser | null>(null)
const deactivateTarget = ref<AdminUser | null>(null)
const selectedUsers = ref<AdminUser[]>([])
const userTableRef = ref<{ clearSelection: () => void } | null>(null)

function todayString() {
  const d = new Date()
  return new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 10)
}

const isSuperAdmin = computed(() => !!auth.user?.is_superuser)
const isUnitScope = computed(() => !isSuperAdmin.value || overview.value?.scope === 'UNIT')

const createForm = reactive<AdminUserCreateIn & { assignment: AdminPermissionAssignment }>({
  username: '',
  password: '',
  name: '',
  employee_no: '',
  phone: '',
  email: '',
  title: '',
  hire_date: '',
  org_id: '',
  is_superuser: false,
  is_unit_admin: false,
  assignment: {
    project_id: '',
    unit_code: null,
    stage_scope: [],
    responsibility: null,
  },
})

const permissionForm = reactive<AdminPermissionAssignment>({
  project_id: '',
  unit_code: null,
  stage_scope: [],
  responsibility: null,
})

const resetForm = reactive({ password: '' })
const editForm = reactive({
  name: '',
  employee_no: '',
  phone: '',
  email: '',
  title: '',
  hire_date: '',
  leave_date: '',
  disable_reason: '',
  is_unit_admin: false,
})

const bulkCreateForm = reactive({
  org_id: '',
  hire_date: '',
  assignment: {
    project_id: '',
    unit_code: null as UnitCode | null,
    stage_scope: [] as StageCode[],
    responsibility: null as Responsibility | null,
  },
})
const bulkRows = ref<AdminBulkUserItem[]>([])

const deactivateForm = reactive({
  leave_date: '',
  disable_reason: '',
})
const bulkDisableForm = reactive({
  leave_date: '',
  disable_reason: '',
})

function emptyBulkUser(): AdminBulkUserItem {
  return {
    username: '',
    password: '',
    name: '',
    employee_no: '',
    phone: '',
    email: '',
    title: '',
  }
}

const selectedCreateOrg = computed(() =>
  options.value?.orgs.find((o) => o.id === createForm.org_id),
)

function stagesForUnit(unit?: UnitCode | null) {
  const all = options.value?.stages || []
  if (!unit) return all
  const allowed = options.value?.unit_stages?.[unit]
  if (!allowed?.length) return all
  return all.filter((s) => allowed.includes(s.code))
}

const createStageOptions = computed(() =>
  stagesForUnit(createForm.assignment.unit_code as UnitCode | null),
)
const permissionStageOptions = computed(() =>
  stagesForUnit(permissionForm.unit_code as UnitCode | null),
)
const bulkStageOptions = computed(() =>
  stagesForUnit(bulkCreateForm.assignment.unit_code),
)

onMounted(loadAll)

async function loadAll() {
  loading.value = true
  try {
    const [ov, opts, list] = await Promise.all([
      adminApi.overview(),
      adminApi.options(),
      adminApi.users(keyword.value || undefined),
    ])
    overview.value = ov
    options.value = opts
    users.value = list
    selectedUsers.value = []
    await nextTick()
    userTableRef.value?.clearSelection()
  } catch (e) {
    ElMessage.error(explainApiError(e))
  } finally {
    loading.value = false
  }
}

async function loadUsers() {
  loading.value = true
  try {
    users.value = await adminApi.users(keyword.value || undefined)
    selectedUsers.value = []
    await nextTick()
    userTableRef.value?.clearSelection()
  } catch (e) {
    ElMessage.error(explainApiError(e))
  } finally {
    loading.value = false
  }
}

function openCreate() {
  Object.assign(createForm, {
    username: '',
    password: '',
    name: '',
    employee_no: '',
    phone: '',
    email: '',
    title: '',
    hire_date: todayString(),
    org_id: options.value?.orgs[0]?.id || '',
    is_superuser: false,
    is_unit_admin: false,
    assignment: {
      project_id: '',
      unit_code: options.value?.orgs[0]?.unit_code as UnitCode | null,
      stage_scope: [],
      responsibility: null,
    },
  })
  createVisible.value = true
}

function onCreateOrgChange() {
  createForm.assignment.unit_code = (selectedCreateOrg.value?.unit_code as UnitCode | null) || null
  const allowed = new Set(createStageOptions.value.map((s) => s.code))
  createForm.assignment.stage_scope = (createForm.assignment.stage_scope || []).filter((s) =>
    allowed.has(s),
  )
}

async function submitCreate() {
  if (!createForm.username.trim() || !createForm.password || !createForm.name.trim() || !createForm.org_id) {
    ElMessage.warning('请填写账号、姓名、密码和所属单位')
    return
  }
  saving.value = true
  try {
    const assignments: AdminPermissionAssignment[] = []
    if (createForm.assignment.project_id) {
      assignments.push({
        project_id: createForm.assignment.project_id,
        unit_code: createForm.assignment.unit_code,
        stage_scope: createForm.assignment.stage_scope,
        responsibility: createForm.assignment.responsibility,
      })
    }
    await adminApi.createUser({
      username: createForm.username.trim(),
      password: createForm.password,
      name: createForm.name.trim(),
      employee_no: createForm.employee_no,
      phone: createForm.phone,
      email: createForm.email,
      title: createForm.title,
      hire_date: createForm.hire_date || null,
      org_id: createForm.org_id,
      is_superuser: isSuperAdmin.value ? createForm.is_superuser : false,
      is_unit_admin: isSuperAdmin.value ? createForm.is_unit_admin : false,
      assignments,
    })
    ElMessage.success('账号已创建；员工首次登录必须修改初始密码')
    createVisible.value = false
    await loadAll()
  } catch (e) {
    ElMessage.error(explainApiError(e))
  } finally {
    saving.value = false
  }
}

function openPermission(user: AdminUser) {
  if (!user.is_active) {
    ElMessage.warning('账号已停用，请先启用账号后再分配项目权限')
    return
  }
  targetUser.value = user
  Object.assign(permissionForm, {
    project_id: options.value?.projects[0]?.id || '',
    unit_code: (user.orgs[0]?.unit_code as UnitCode | null) || null,
    stage_scope: [],
    responsibility: null,
  })
  permissionVisible.value = true
}

function openMemberships(user: AdminUser) {
  targetUser.value = user
  membershipVisible.value = true
}

function continueAssignFromMemberships() {
  if (!targetUser.value) return
  membershipVisible.value = false
  openPermission(targetUser.value)
}

async function submitPermission() {
  if (!targetUser.value || !permissionForm.project_id) {
    ElMessage.warning('请选择项目')
    return
  }
  saving.value = true
  try {
    await adminApi.assignPermission(targetUser.value.id, {
      project_id: permissionForm.project_id,
      unit_code: permissionForm.unit_code,
      stage_scope: permissionForm.stage_scope,
      responsibility: isSuperAdmin.value ? permissionForm.responsibility : null,
    })
    ElMessage.success('项目权限已分配')
    permissionVisible.value = false
    await loadAll()
  } catch (e) {
    ElMessage.error(explainApiError(e))
  } finally {
    saving.value = false
  }
}

function openEdit(user: AdminUser) {
  targetUser.value = user
  Object.assign(editForm, {
    name: user.name || '',
    employee_no: user.employee_no || '',
    phone: user.phone || '',
    email: user.email || '',
    title: user.title || '',
    hire_date: user.hire_date || '',
    leave_date: user.leave_date || '',
    disable_reason: user.disable_reason || '',
    is_unit_admin: user.orgs[0]?.is_unit_admin || false,
  })
  editVisible.value = true
}

async function submitEdit() {
  if (!targetUser.value || !editForm.name.trim()) {
    ElMessage.warning('姓名不能为空')
    return
  }
  saving.value = true
  try {
    const payload = {
      name: editForm.name.trim(),
      employee_no: editForm.employee_no || null,
      phone: editForm.phone || null,
      email: editForm.email || null,
      title: editForm.title || null,
      hire_date: editForm.hire_date || null,
      leave_date: editForm.leave_date || null,
      disable_reason: editForm.disable_reason || null,
    }
    await adminApi.updateUser(
      targetUser.value.id,
      isSuperAdmin.value ? { ...payload, is_unit_admin: editForm.is_unit_admin } : payload,
    )
    ElMessage.success('员工资料已更新')
    editVisible.value = false
    await loadAll()
  } catch (e) {
    ElMessage.error(explainApiError(e))
  } finally {
    saving.value = false
  }
}

function openReset(user: AdminUser) {
  targetUser.value = user
  resetForm.password = ''
  resetVisible.value = true
}

async function submitReset() {
  if (!targetUser.value || resetForm.password.length < 6) {
    ElMessage.warning('密码至少 6 位')
    return
  }
  saving.value = true
  try {
    await adminApi.resetPassword(targetUser.value.id, resetForm.password)
    ElMessage.success('密码已重置；用户下次登录必须先修改密码')
    resetVisible.value = false
  } catch (e) {
    ElMessage.error(explainApiError(e))
  } finally {
    saving.value = false
  }
}

function openDeactivate(user: AdminUser) {
  deactivateTarget.value = user
  Object.assign(deactivateForm, {
    leave_date: todayString(),
    disable_reason: '离职',
  })
  deactivateVisible.value = true
}

async function submitDeactivate() {
  if (!deactivateTarget.value) return
  saving.value = true
  try {
    await adminApi.updateUser(deactivateTarget.value.id, {
      is_active: false,
      leave_date: deactivateForm.leave_date || todayString(),
      disable_reason: deactivateForm.disable_reason || '离职',
    })
    ElMessage.success('账号已停用，项目权限已吊销')
    deactivateVisible.value = false
    await loadAll()
  } catch (e) {
    ElMessage.error(explainApiError(e))
  } finally {
    saving.value = false
  }
}

async function toggleActive(user: AdminUser) {
  if (user.is_active) {
    openDeactivate(user)
    return
  }
  try {
    await ElMessageBox.confirm(
      `确定重新启用账号「${user.name}」吗？停用信息会清空，项目权限需要重新分配。`,
      '启用账号',
      { type: 'warning' },
    )
    await adminApi.updateUser(user.id, { is_active: true })
    ElMessage.success('账号已启用，请重新分配项目权限')
    await loadAll()
  } catch (e) {
    if (e !== 'cancel' && e !== 'close') ElMessage.error(explainApiError(e))
  }
}

function canManageRow(user: AdminUser) {
  if (isSuperAdmin.value) return true
  if (user.is_superuser) return false
  return !isUnitAdmin(user) || user.id === auth.user?.id
}

function canAssignPermission(user: AdminUser) {
  return user.is_active && canManageRow(user)
}

function handleSelectionChange(rows: AdminUser[]) {
  selectedUsers.value = rows
}

function canSelectForDisable(user: AdminUser) {
  return (
    user.is_active &&
    !user.is_superuser &&
    !isUnitAdmin(user) &&
    user.id !== auth.user?.id &&
    canManageRow(user)
  )
}

function openBulkCreate() {
  const firstOrg = options.value?.orgs[0]
  bulkRows.value = [emptyBulkUser()]
  Object.assign(bulkCreateForm, {
    org_id: firstOrg?.id || '',
    hire_date: todayString(),
    assignment: {
      project_id: '',
      unit_code: (firstOrg?.unit_code as UnitCode | null) || null,
      stage_scope: [],
      responsibility: null,
    },
  })
  bulkCreateVisible.value = true
}

function addBulkRow() {
  bulkRows.value.push(emptyBulkUser())
}

function removeBulkRow(index: number) {
  if (bulkRows.value.length <= 1) {
    bulkRows.value[0] = emptyBulkUser()
    return
  }
  bulkRows.value.splice(index, 1)
}

function onBulkOrgChange() {
  const org = options.value?.orgs.find((o) => o.id === bulkCreateForm.org_id)
  bulkCreateForm.assignment.unit_code = (org?.unit_code as UnitCode | null) || null
  const allowed = new Set(bulkStageOptions.value.map((s) => s.code))
  bulkCreateForm.assignment.stage_scope = bulkCreateForm.assignment.stage_scope.filter((s) =>
    allowed.has(s),
  )
}

async function submitBulkCreate() {
  if (!bulkCreateForm.org_id || bulkRows.value.length === 0) {
    ElMessage.warning('请选择所属单位并至少填写一名员工')
    return
  }
  for (let i = 0; i < bulkRows.value.length; i += 1) {
    const row = bulkRows.value[i]
    if (!row.username.trim() || !row.password || !row.name.trim()) {
      ElMessage.warning(`第 ${i + 1} 行请填写登录账号、姓名和初始密码`)
      return
    }
  }
  saving.value = true
  try {
    const assignments: AdminPermissionAssignment[] = []
    if (bulkCreateForm.assignment.project_id) {
      assignments.push({
        project_id: bulkCreateForm.assignment.project_id,
        unit_code: bulkCreateForm.assignment.unit_code,
        stage_scope: bulkCreateForm.assignment.stage_scope,
        responsibility: null,
      })
    }
    const result = await adminApi.bulkCreateUsers({
      org_id: bulkCreateForm.org_id,
      hire_date: bulkCreateForm.hire_date || null,
      users: bulkRows.value.map((row) => ({
        username: row.username.trim(),
        password: row.password,
        name: row.name.trim(),
        employee_no: row.employee_no || null,
        phone: row.phone || null,
        email: row.email || null,
        title: row.title || null,
      })),
      assignments,
    })
    ElMessage.success(`已批量创建 ${result.created_count} 个账号；首次登录必须修改初始密码`)
    bulkCreateVisible.value = false
    await loadAll()
  } catch (e) {
    ElMessage.error(explainApiError(e))
  } finally {
    saving.value = false
  }
}

function openBulkDeactivate() {
  if (selectedUsers.value.length === 0) {
    ElMessage.warning('请先勾选要停用的员工')
    return
  }
  Object.assign(bulkDisableForm, {
    leave_date: todayString(),
    disable_reason: '离职',
  })
  bulkDeactivateVisible.value = true
}

async function submitBulkDeactivate() {
  if (selectedUsers.value.length === 0) return
  saving.value = true
  try {
    const result = await adminApi.bulkDeactivateUsers({
      user_ids: selectedUsers.value.map((u) => u.id),
      leave_date: bulkDisableForm.leave_date || todayString(),
      disable_reason: bulkDisableForm.disable_reason || '离职',
    })
    ElMessage.success(`已批量停用 ${result.disabled_count} 个账号`)
    bulkDeactivateVisible.value = false
    await loadAll()
  } catch (e) {
    ElMessage.error(explainApiError(e))
  } finally {
    saving.value = false
  }
}

async function revokeMembership(user: AdminUser, membership: AdminMembership) {
  try {
    await ElMessageBox.confirm(
      `确定取消「${user.name}」在「${membership.project_name || membership.project_id}」的项目权限吗？账号不会被删除。`,
      '取消项目权限',
      { type: 'warning' },
    )
    await adminApi.revokePermission(user.id, membership.id)
    ElMessage.success('项目权限已取消')
    membershipVisible.value = false
    await loadAll()
  } catch (e) {
    if (e !== 'cancel' && e !== 'close') ElMessage.error(explainApiError(e))
  }
}

function membershipStageText(membership: AdminMembership) {
  if (!options.value) return '—'
  const labels = new Map(options.value.stages.map((s) => [s.code, s.label]))
  if (membership.stage_scope.length === options.value.stages.length) return '全部阶段'
  return membership.stage_scope.map((s) => labels.get(s as StageCode) || s).join('、') || '—'
}

function orgNames(user: AdminUser) {
  return user.orgs.map((o) => o.name).join('、') || '未分配单位'
}

function projectCount(user: AdminUser) {
  return new Set(user.memberships.map((m) => m.project_id)).size
}

function permissionUnits(user: AdminUser) {
  return Array.from(new Set(user.memberships.map((m) => m.unit_label).filter(Boolean)))
}

function isUnitAdmin(user: AdminUser) {
  return user.orgs.some((o) => o.is_unit_admin)
}

function stageScopeText(user: AdminUser) {
  if (!options.value) return '—'
  const labels = new Map(options.value.stages.map((s) => [s.code, s.label]))
  const allStages = user.memberships.flatMap((m) => m.stage_scope)
  const unique = Array.from(new Set(allStages))
  if (unique.length === options.value.stages.length) return '全部阶段'
  return unique.map((s) => labels.get(s as StageCode) || s).join('、') || '未分配'
}
</script>

<template>
  <div class="admin-page">
    <header class="admin-hero">
      <div>
        <div class="hero-kicker">{{ isUnitScope ? 'DEPARTMENT ADMINISTRATION' : 'SYSTEM ADMINISTRATION' }}</div>
        <h2>{{ isUnitScope ? '部门权限管理' : '系统管理控制台' }}</h2>
        <p v-if="isUnitScope">
          管理本部门员工账号，把员工加入本部门参与的项目，并分配本部门负责的阶段权限。
        </p>
        <p v-else>创建员工账号、指定所属单位，并分配项目与阶段权限。</p>
      </div>
      <div v-if="isUnitScope && overview?.managed_org_names?.length" class="hero-scope">
        {{ overview.managed_org_names.join('、') }}
      </div>
    </header>

    <section class="admin-stats">
      <div>
        <span>{{ isUnitScope ? '本部门账号' : '账号总数' }}</span>
        <b>{{ overview?.user_count ?? 0 }}</b>
        <small>启用 {{ overview?.active_user_count ?? 0 }}</small>
      </div>
      <div>
        <span>{{ isUnitScope ? '部门管理员' : '管理员' }}</span>
        <b>{{ overview?.admin_count ?? 0 }}</b>
        <small>{{ isUnitScope ? '本部门管理账号' : '系统控制权限' }}</small>
      </div>
      <div>
        <span>{{ isUnitScope ? '管理部门' : '参与单位' }}</span>
        <b>{{ overview?.org_count ?? 0 }}</b>
        <small>{{ isUnitScope ? '仅限本部门范围' : '已配置组织' }}</small>
      </div>
      <div>
        <span>权限关系</span>
        <b>{{ overview?.membership_count ?? 0 }}</b>
        <small>有效项目成员配置</small>
      </div>
    </section>

    <section class="user-panel app-card">
      <div class="panel-head">
        <div>
          <h3>{{ isUnitScope ? '本部门员工账号与权限' : '员工账号与权限' }}</h3>
          <p v-if="isUnitScope">可单个或批量创建本部门账号；停用账号会同时取消全部项目权限。</p>
          <p v-else>支持批量入职、批量停用，以及单个账号的项目权限管理。</p>
        </div>
        <div class="panel-actions">
          <el-input
            v-model="keyword"
            clearable
            placeholder="搜索姓名、账号、工号"
            class="search"
            @keyup.enter="loadUsers"
            @clear="loadUsers"
          >
            <template #prefix><el-icon><Search /></el-icon></template>
          </el-input>
          <el-button @click="loadUsers">查询</el-button>
          <el-button type="primary" @click="openCreate">
            <el-icon><Plus /></el-icon>
            创建账号
          </el-button>
          <el-button @click="openBulkCreate">批量入职</el-button>
          <el-button
            type="warning"
            plain
            :disabled="selectedUsers.length === 0"
            @click="openBulkDeactivate"
          >
            批量停用{{ selectedUsers.length ? `（${selectedUsers.length}）` : '' }}
          </el-button>
        </div>
      </div>

      <el-table
        ref="userTableRef"
        v-loading="loading"
        :data="users"
        row-key="id"
        class="user-table"
        @selection-change="handleSelectionChange"
      >
        <el-table-column type="selection" width="44" :selectable="canSelectForDisable" />
        <el-table-column label="账号" min-width="220">
          <template #default="{ row }">
            <div class="account-cell">
              <span class="avatar">{{ row.name?.charAt(0) || '?' }}</span>
              <div>
                <div class="name-line">
                  {{ row.name }}
                  <el-tag v-if="row.is_superuser" size="small" type="danger" effect="plain">管理员</el-tag>
                  <el-tag v-else size="small" type="info" effect="plain">员工</el-tag>
                  <el-tag
                    v-if="isUnitAdmin(row)"
                    size="small"
                    type="warning"
                    effect="plain"
                  >
                    部门管理员
                  </el-tag>
                  <el-tag
                    v-if="row.must_change_password"
                    size="small"
                    type="warning"
                    effect="plain"
                  >
                    待改密
                  </el-tag>
                </div>
                <div class="sub">{{ row.username }}<template v-if="row.employee_no"> · {{ row.employee_no }}</template></div>
              </div>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="所属单位" min-width="210">
          <template #default="{ row }">
            <div>{{ orgNames(row) }}</div>
            <div v-if="row.title" class="sub">{{ row.title }}</div>
            <div v-if="row.hire_date" class="sub">入职 {{ row.hire_date }}</div>
            <div v-if="row.leave_date" class="sub">离职 {{ row.leave_date }}</div>
            <div v-if="row.disable_reason && !row.is_active" class="sub">
              停用原因：{{ row.disable_reason }}
            </div>
            <div v-if="row.last_password_changed_at" class="sub">
              最近改密 {{ row.last_password_changed_at.slice(0, 10) }}
            </div>
          </template>
        </el-table-column>
        <el-table-column label="项目权限" min-width="240">
          <template #default="{ row }">
            <div class="permission-units">
              {{ permissionUnits(row).join('、') || '未分配参与单位' }}
            </div>
            <div class="sub scope-text">
              {{ projectCount(row) }} 个项目 · {{ stageScopeText(row) }}
            </div>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="150" align="center">
          <template #default="{ row }">
            <el-tag :type="row.is_active ? 'success' : 'danger'" size="small" effect="light">
              {{ row.is_active ? '启用' : '已停用' }}
            </el-tag>
            <div v-if="!row.is_active && row.disabled_by_name" class="sub">
              由 {{ row.disabled_by_name }} 停用
            </div>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="430" fixed="right">
          <template #default="{ row }">
            <el-button link @click="openMemberships(row)">项目权限</el-button>
            <el-button
              v-if="canAssignPermission(row)"
              link
              type="primary"
              @click="openPermission(row)"
            >
              分配权限
            </el-button>
            <el-button v-if="canManageRow(row)" link @click="openEdit(row)">编辑资料</el-button>
            <el-button v-if="isSuperAdmin" link @click="openReset(row)">重置密码</el-button>
            <el-button
              v-if="canManageRow(row)"
              link
              :type="row.is_active ? 'danger' : 'success'"
              :disabled="row.id === auth.user?.id"
              @click="toggleActive(row)"
            >
              {{ row.is_active ? '停用' : '启用' }}
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </section>

    <!-- 创建账号 -->
    <el-dialog v-model="createVisible" title="创建员工账号" width="760px" destroy-on-close>
      <el-alert
        v-if="isUnitScope"
        type="info"
        :closable="false"
        show-icon
        class="scope-alert"
        title="部门管理员只能在本部门创建账号；初始密码由你设置，新账号首次登录必须修改密码。"
      />
      <el-alert
        v-if="isSuperAdmin"
        type="info"
        :closable="false"
        show-icon
        class="scope-alert"
        title="新账号首次登录必须修改初始密码；管理员重置密码后也会要求再次修改。"
      />
      <el-form label-position="top" :model="createForm">
        <div class="form-grid">
          <el-form-item label="登录账号 *">
            <el-input v-model="createForm.username" placeholder="例如：zhangsan" />
          </el-form-item>
          <el-form-item label="初始密码 *">
            <el-input v-model="createForm.password" type="password" show-password placeholder="至少 6 位" />
          </el-form-item>
          <el-form-item label="姓名 *">
            <el-input v-model="createForm.name" placeholder="员工姓名" />
          </el-form-item>
          <el-form-item label="工号">
            <el-input v-model="createForm.employee_no" />
          </el-form-item>
          <el-form-item label="手机">
            <el-input v-model="createForm.phone" />
          </el-form-item>
          <el-form-item label="邮箱">
            <el-input v-model="createForm.email" />
          </el-form-item>
          <el-form-item label="职称">
            <el-input v-model="createForm.title" />
          </el-form-item>
          <el-form-item label="入职日期">
            <el-date-picker
              v-model="createForm.hire_date"
              type="date"
              value-format="YYYY-MM-DD"
              placeholder="选择入职日期"
              style="width: 100%"
            />
          </el-form-item>
          <el-form-item label="所属单位 *">
            <el-select v-model="createForm.org_id" style="width: 100%" @change="onCreateOrgChange">
              <el-option v-for="o in options?.orgs || []" :key="o.id" :label="o.name" :value="o.id" />
            </el-select>
          </el-form-item>
        </div>

        <div class="permission-box">
          <div class="box-title">初始项目权限（可选）</div>
          <div class="form-grid">
            <el-form-item label="参与项目">
              <el-select v-model="createForm.assignment.project_id" clearable style="width: 100%">
                <el-option
                  v-for="p in options?.projects || []"
                  :key="p.id"
                  :label="`${p.project_no} · ${p.name}`"
                  :value="p.id"
                />
              </el-select>
            </el-form-item>
            <el-form-item label="参与单位">
              <el-select v-model="createForm.assignment.unit_code" disabled style="width: 100%">
                <el-option v-for="u in options?.units || []" :key="u.code" :label="u.label" :value="u.code" />
              </el-select>
            </el-form-item>
            <el-form-item label="可见阶段">
              <el-select
                v-model="createForm.assignment.stage_scope"
                multiple
                collapse-tags
                clearable
                :placeholder="isUnitScope ? '不选表示本部门负责的全部阶段' : '不选表示全部阶段'"
                style="width: 100%"
              >
                <el-option v-for="s in createStageOptions" :key="s.code" :label="s.label" :value="s.code" />
              </el-select>
            </el-form-item>
            <el-form-item v-if="isSuperAdmin" label="阶段责任覆盖">
              <el-select
                v-model="createForm.assignment.responsibility"
                clearable
                placeholder="不覆盖则按标准矩阵"
                style="width: 100%"
              >
                <el-option
                  v-for="r in options?.responsibilities || []"
                  :key="r.code"
                  :label="r.label"
                  :value="r.code"
                />
              </el-select>
            </el-form-item>
          </div>
        </div>

        <div v-if="isSuperAdmin" class="admin-checks">
          <el-checkbox v-model="createForm.is_unit_admin">设为部门管理员（领导）</el-checkbox>
          <el-checkbox v-model="createForm.is_superuser">创建为系统管理员</el-checkbox>
        </div>
      </el-form>
      <template #footer>
        <el-button @click="createVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="submitCreate">创建账号</el-button>
      </template>
    </el-dialog>

    <!-- 批量入职 -->
    <el-dialog v-model="bulkCreateVisible" title="批量入职" width="1100px" destroy-on-close>
      <el-alert
        type="info"
        :closable="false"
        show-icon
        class="scope-alert"
        title="批量创建的账号首次登录必须修改初始密码；工号、邮箱和登录账号不能重复。"
      />
      <el-form label-position="top">
        <div class="form-grid">
          <el-form-item label="所属单位 *">
            <el-select v-model="bulkCreateForm.org_id" style="width: 100%" @change="onBulkOrgChange">
              <el-option v-for="o in options?.orgs || []" :key="o.id" :label="o.name" :value="o.id" />
            </el-select>
          </el-form-item>
          <el-form-item label="入职日期">
            <el-date-picker
              v-model="bulkCreateForm.hire_date"
              type="date"
              value-format="YYYY-MM-DD"
              placeholder="选择入职日期"
              style="width: 100%"
            />
          </el-form-item>
          <el-form-item label="统一初始项目权限（可选）">
            <el-select v-model="bulkCreateForm.assignment.project_id" clearable style="width: 100%">
              <el-option
                v-for="p in options?.projects || []"
                :key="p.id"
                :label="`${p.project_no} · ${p.name}`"
                :value="p.id"
              />
            </el-select>
          </el-form-item>
          <el-form-item label="参与单位">
            <el-select v-model="bulkCreateForm.assignment.unit_code" disabled style="width: 100%">
              <el-option v-for="u in options?.units || []" :key="u.code" :label="u.label" :value="u.code" />
            </el-select>
          </el-form-item>
          <el-form-item label="统一可见阶段" class="span-2">
            <el-select
              v-model="bulkCreateForm.assignment.stage_scope"
              multiple
              collapse-tags
              clearable
              :placeholder="isUnitScope ? '不选表示本部门负责的全部阶段' : '不选表示全部阶段'"
              style="width: 100%"
            >
              <el-option v-for="s in bulkStageOptions" :key="s.code" :label="s.label" :value="s.code" />
            </el-select>
          </el-form-item>
        </div>
      </el-form>

      <div class="bulk-head">
        <b>员工清单（{{ bulkRows.length }} 人）</b>
        <el-button link type="primary" @click="addBulkRow">+ 添加一行</el-button>
      </div>
      <el-table :data="bulkRows" size="small" border>
        <el-table-column label="登录账号 *" min-width="130">
          <template #default="{ row }"><el-input v-model="row.username" placeholder="zhangsan" /></template>
        </el-table-column>
        <el-table-column label="姓名 *" min-width="110">
          <template #default="{ row }"><el-input v-model="row.name" placeholder="员工姓名" /></template>
        </el-table-column>
        <el-table-column label="工号" min-width="110">
          <template #default="{ row }"><el-input v-model="row.employee_no" /></template>
        </el-table-column>
        <el-table-column label="邮箱" min-width="170">
          <template #default="{ row }"><el-input v-model="row.email" /></template>
        </el-table-column>
        <el-table-column label="初始密码 *" min-width="130">
          <template #default="{ row }"><el-input v-model="row.password" type="password" show-password /></template>
        </el-table-column>
        <el-table-column label="手机" min-width="120">
          <template #default="{ row }"><el-input v-model="row.phone" /></template>
        </el-table-column>
        <el-table-column label="职称" min-width="110">
          <template #default="{ row }"><el-input v-model="row.title" /></template>
        </el-table-column>
        <el-table-column label="操作" width="70" align="center">
          <template #default="{ $index }">
            <el-button link type="danger" @click="removeBulkRow($index)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
      <template #footer>
        <el-button @click="bulkCreateVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="submitBulkCreate">
          批量创建 {{ bulkRows.length }} 个账号
        </el-button>
      </template>
    </el-dialog>

    <!-- 单个停用 -->
    <el-dialog v-model="deactivateVisible" title="停用员工账号" width="500px">
      <div v-if="deactivateTarget" class="target-user">
        <b>{{ deactivateTarget.name }}</b>
        <span>{{ deactivateTarget.username }} · {{ orgNames(deactivateTarget) }}</span>
      </div>
      <el-alert
        type="warning"
        :closable="false"
        show-icon
        class="scope-alert"
        title="停用后会立即吊销全部项目权限，账号和历史记录保留。"
      />
      <el-form label-position="top" :model="deactivateForm">
        <el-form-item label="离职/停用日期">
          <el-date-picker
            v-model="deactivateForm.leave_date"
            type="date"
            value-format="YYYY-MM-DD"
            style="width: 100%"
          />
        </el-form-item>
        <el-form-item label="停用原因">
          <el-input v-model="deactivateForm.disable_reason" placeholder="例如：离职、调岗、长期借调结束" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="deactivateVisible = false">取消</el-button>
        <el-button type="danger" :loading="saving" @click="submitDeactivate">确认停用</el-button>
      </template>
    </el-dialog>

    <!-- 批量停用 -->
    <el-dialog v-model="bulkDeactivateVisible" title="批量停用员工账号" width="500px">
      <el-alert
        type="warning"
        :closable="false"
        show-icon
        class="scope-alert"
        :title="`已选择 ${selectedUsers.length} 名员工，确认后会立即吊销全部项目权限。`"
      />
      <el-form label-position="top" :model="bulkDisableForm">
        <el-form-item label="统一离职/停用日期">
          <el-date-picker
            v-model="bulkDisableForm.leave_date"
            type="date"
            value-format="YYYY-MM-DD"
            style="width: 100%"
          />
        </el-form-item>
        <el-form-item label="统一停用原因">
          <el-input v-model="bulkDisableForm.disable_reason" placeholder="例如：离职、业务调整" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="bulkDeactivateVisible = false">取消</el-button>
        <el-button type="danger" :loading="saving" @click="submitBulkDeactivate">
          确认批量停用
        </el-button>
      </template>
    </el-dialog>

    <!-- 分配权限 -->
    <el-dialog v-model="permissionVisible" title="分配项目权限" width="620px" destroy-on-close>
      <div v-if="targetUser" class="target-user">
        <b>{{ targetUser.name }}</b>
        <span>{{ targetUser.username }} · {{ orgNames(targetUser) }}</span>
      </div>
      <el-alert
        v-if="isUnitScope"
        type="info"
        :closable="false"
        show-icon
        class="scope-alert"
        title="只能分配本部门参与的项目；阶段范围限定为《管理流程》中本部门有责任的阶段。"
      />
      <el-form label-position="top" :model="permissionForm">
        <el-form-item label="参与项目 *">
          <el-select v-model="permissionForm.project_id" style="width: 100%">
            <el-option
              v-for="p in options?.projects || []"
              :key="p.id"
              :label="`${p.project_no} · ${p.name}`"
              :value="p.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="参与单位">
          <el-select v-model="permissionForm.unit_code" disabled style="width: 100%">
            <el-option v-for="u in options?.units || []" :key="u.code" :label="u.label" :value="u.code" />
          </el-select>
        </el-form-item>
        <el-form-item label="可见阶段">
          <el-select
            v-model="permissionForm.stage_scope"
            multiple
            collapse-tags
            clearable
            :placeholder="isUnitScope ? '不选表示本部门负责的全部阶段' : '不选表示全部阶段'"
            style="width: 100%"
          >
            <el-option v-for="s in permissionStageOptions" :key="s.code" :label="s.label" :value="s.code" />
          </el-select>
        </el-form-item>
        <el-form-item v-if="isSuperAdmin" label="阶段责任覆盖">
          <el-select
            v-model="permissionForm.responsibility"
            clearable
            placeholder="不覆盖则按标准矩阵"
            style="width: 100%"
          >
            <el-option v-for="r in options?.responsibilities || []" :key="r.code" :label="r.label" :value="r.code" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="permissionVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="submitPermission">保存权限</el-button>
      </template>
    </el-dialog>

    <!-- 管理员编辑员工资料 -->
    <el-dialog v-model="editVisible" title="编辑员工资料" width="620px">
      <div v-if="targetUser" class="target-user">
        <b>{{ targetUser.username }}</b>
        <span>{{ orgNames(targetUser) }}</span>
      </div>
      <el-form label-position="top" :model="editForm">
        <div class="form-grid">
          <el-form-item label="姓名 *">
            <el-input v-model="editForm.name" />
          </el-form-item>
          <el-form-item label="工号">
            <el-input v-model="editForm.employee_no" />
          </el-form-item>
          <el-form-item label="职称">
            <el-input v-model="editForm.title" />
          </el-form-item>
          <el-form-item label="手机">
            <el-input v-model="editForm.phone" />
          </el-form-item>
          <el-form-item label="邮箱">
            <el-input v-model="editForm.email" />
          </el-form-item>
          <el-form-item label="入职日期">
            <el-date-picker
              v-model="editForm.hire_date"
              type="date"
              value-format="YYYY-MM-DD"
              placeholder="选择入职日期"
              style="width: 100%"
            />
          </el-form-item>
          <el-form-item v-if="targetUser && !targetUser.is_active" label="离职日期">
            <el-date-picker
              v-model="editForm.leave_date"
              type="date"
              value-format="YYYY-MM-DD"
              placeholder="选择离职日期"
              style="width: 100%"
            />
          </el-form-item>
          <el-form-item v-if="targetUser && !targetUser.is_active" label="停用原因">
            <el-input v-model="editForm.disable_reason" placeholder="例如：离职、调岗" />
          </el-form-item>
        </div>
        <el-checkbox v-if="isSuperAdmin" v-model="editForm.is_unit_admin">
          设为部门管理员（领导）
        </el-checkbox>
      </el-form>
      <template #footer>
        <el-button @click="editVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="submitEdit">保存资料</el-button>
      </template>
    </el-dialog>

    <!-- 项目权限明细 -->
    <el-dialog v-model="membershipVisible" title="项目权限明细" width="720px">
      <div v-if="targetUser" class="target-user">
        <b>{{ targetUser.name }}</b>
        <span>{{ targetUser.username }} · {{ orgNames(targetUser) }}</span>
      </div>
      <el-empty v-if="!targetUser?.memberships?.length" description="暂无有效项目权限" />
      <el-table v-else :data="targetUser.memberships" size="small">
        <el-table-column label="项目" min-width="230">
          <template #default="{ row }">
            <div>{{ row.project_name || '—' }}</div>
            <div class="sub">{{ row.project_no || row.project_id }}</div>
          </template>
        </el-table-column>
        <el-table-column label="参与单位" width="150">
          <template #default="{ row }">{{ row.unit_label || row.unit_code }}</template>
        </el-table-column>
        <el-table-column label="阶段权限" min-width="220">
          <template #default="{ row }">{{ membershipStageText(row) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="100" align="right">
          <template #default="{ row }">
            <el-button
              v-if="targetUser && canManageRow(targetUser)"
              link
              type="danger"
              @click="revokeMembership(targetUser, row)"
            >
              取消权限
            </el-button>
          </template>
        </el-table-column>
      </el-table>
      <template #footer>
        <el-button @click="membershipVisible = false">关闭</el-button>
        <el-button
          type="primary"
          :disabled="!targetUser || !canAssignPermission(targetUser)"
          @click="continueAssignFromMemberships"
        >
          继续分配权限
        </el-button>
      </template>
    </el-dialog>

    <!-- 重置密码 -->
    <el-dialog v-model="resetVisible" title="重置密码" width="430px">
      <p class="reset-user">为「{{ targetUser?.name }}」设置新密码</p>
      <el-alert
        type="warning"
        :closable="false"
        show-icon
        class="scope-alert"
        title="重置后旧会话会立即失效，用户下次登录必须先修改密码。"
      />
      <el-input v-model="resetForm.password" type="password" show-password placeholder="至少 6 位" />
      <template #footer>
        <el-button @click="resetVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="submitReset">确认重置</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.admin-page {
  max-width: 1540px;
  margin: 0 auto;
}

:global(.el-dialog) {
  max-width: calc(100vw - 24px);
}

.admin-hero {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 20px;
  padding: 22px 24px;
  border-radius: 12px;
  color: #fff;
  background: linear-gradient(120deg, #102d53, #1a5b9e 70%, #0f8f8a);
  box-shadow: 0 12px 30px rgba(16, 45, 83, 0.18);
}

.hero-kicker {
  color: #bfe0ff;
  font-size: 10.5px;
  font-weight: 800;
  letter-spacing: 2px;
}

.admin-hero h2 {
  margin: 4px 0 4px;
  font-size: 25px;
}

.admin-hero p {
  margin: 0;
  color: #d9e9f8;
  font-size: 13px;
}

.admin-stats {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 13px;
  margin-top: 16px;
}

.admin-stats > div {
  padding: 14px 17px;
  border: 1px solid #dde4ec;
  border-radius: 10px;
  background: #fff;
}

.admin-stats span,
.admin-stats small {
  display: block;
  color: #738095;
  font-size: 11.5px;
}

.admin-stats b {
  display: block;
  margin: 3px 0;
  color: #1f2a3d;
  font-size: 24px;
  line-height: 1.2;
}

.user-panel {
  margin-top: 16px;
  padding: 18px 20px 12px;
}

.panel-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 18px;
  margin-bottom: 14px;
}

.panel-head h3 {
  margin: 0;
  color: #1f2a3d;
  font-size: 17px;
}

.panel-head p {
  margin: 4px 0 0;
  color: #738095;
  font-size: 12.5px;
}

.panel-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.search {
  width: 250px;
}

.account-cell {
  display: flex;
  align-items: center;
  gap: 10px;
}

.account-cell .avatar {
  width: 34px;
  height: 34px;
  display: grid;
  place-items: center;
  flex: 0 0 auto;
  border-radius: 9px;
  color: #fff;
  font-size: 14px;
  font-weight: 700;
  background: linear-gradient(135deg, #1a6bb0, #0ea5a4);
}

.name-line {
  display: flex;
  align-items: center;
  gap: 6px;
  color: #1f2a3d;
  font-weight: 600;
}

.sub {
  margin-top: 2px;
  color: #8793a5;
  font-size: 11.5px;
}

.permission-units {
  color: #1f2a3d;
  font-weight: 600;
}

.scope-text {
  max-width: 260px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.form-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  column-gap: 14px;
}

.span-2 {
  grid-column: 1 / -1;
}

.admin-checks {
  display: flex;
  align-items: center;
  gap: 22px;
}

.bulk-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin: 6px 0 10px;
  color: #1f2a3d;
  font-size: 13px;
}

.permission-box {
  margin: 2px 0 12px;
  padding: 14px 14px 0;
  border: 1px solid #dde7f0;
  border-radius: 9px;
  background: #f8fbfe;
}

.box-title {
  margin-bottom: 12px;
  color: #1f2a3d;
  font-size: 13px;
  font-weight: 700;
}

.target-user {
  display: flex;
  align-items: baseline;
  gap: 10px;
  margin-bottom: 14px;
  padding: 10px 12px;
  border-radius: 8px;
  background: #f5f8fc;
}

.target-user span,
.reset-user {
  color: #738095;
  font-size: 12.5px;
}

@media (max-width: 1100px) {
  .admin-stats {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
  .panel-head {
    flex-direction: column;
  }
}

@media (max-width: 720px) {
  .admin-hero {
    align-items: flex-start;
    flex-direction: column;
  }
  .panel-actions {
    width: 100%;
    flex-wrap: wrap;
  }
  .search {
    width: 100%;
  }
  .form-grid {
    grid-template-columns: 1fr;
  }
}
</style>
