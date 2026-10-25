/**
 * 认证与权限状态。
 *
 * 核心原则：**权限信息全部由后端 /auth/me 下发，前端不硬编码任何判断逻辑。**
 * 前端只做"体验优化"（隐藏无权按钮），真正的拦截在后端。
 *
 * 新模型下主体是「参与单位」，所以这里不再有"我在这个项目是什么角色"，
 * 而是"我在这个项目以哪个单位参与、能看哪些阶段、哪些阶段是主办"。
 * 阶段范围来自《管理流程》矩阵，由后端推导后下发。
 */
import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

import { authApi } from '@/api'
import { tokenStore } from '@/api/http'
import type {
  CurrentUser,
  Membership,
  PermissionAction,
  StageCode,
  TokenPair,
  UnitCode,
} from '@/api/types'

export const useAuthStore = defineStore('auth', () => {
  const user = ref<CurrentUser | null>(null)
  const loading = ref(false)

  const isLoggedIn = computed(() => !!user.value && !!tokenStore.access)

  /** 我参与的全部项目 id */
  const myProjectIds = computed(() => user.value?.memberships.map((m) => m.project_id) ?? [])

  /** 我担任管理员的部门（单位） */
  const managedOrgs = computed(() => user.value?.orgs.filter((o) => o.is_unit_admin) ?? [])

  /** 是否是部门管理员 */
  const isUnitAdmin = computed(() => managedOrgs.value.length > 0)

  /** 是否能进入权限管理页面：总管理员或部门管理员 */
  const canManageStaff = computed(() => !!user.value?.is_superuser || isUnitAdmin.value)

  /** 首次登录或管理员重置密码后，必须先修改密码 */
  const mustChangePassword = computed(() => !!user.value?.must_change_password)

  function membershipOf(projectId: string): Membership | undefined {
    return user.value?.memberships.find((m) => m.project_id === projectId)
  }

  /** 我在某项目以哪个单位参与（多重身份时后端已取责任最重的那个） */
  function unitIn(projectId: string): UnitCode | undefined {
    return membershipOf(projectId)?.unit_code
  }

  /** 我在某项目负责的阶段 —— 由矩阵推导，后端下发 */
  function visibleStages(projectId: string): StageCode[] {
    return membershipOf(projectId)?.stages ?? []
  }

  /** 我在某项目是**主办单位**的阶段 —— 这些阶段我能上传、提交、发布 */
  function primaryStages(projectId: string): StageCode[] {
    return membershipOf(projectId)?.primary_stages ?? []
  }

  /** 我是不是某阶段的主办单位 */
  function isPrimaryOf(projectId: string, stage?: StageCode): boolean {
    if (!stage) return false
    return primaryStages(projectId).includes(stage)
  }

  /**
   * 我能否对某项目的某阶段执行某动作。
   *
   * ⚠️ 这只是体验层判断。后端每个接口都会独立校验，
   * 前端隐藏按钮**不是**安全措施。
   */
  function can(projectId: string, action: PermissionAction, stage?: StageCode): boolean {
    if (user.value?.is_superuser) return true
    const m = membershipOf(projectId)
    if (!m) return false
    if (!m.actions.includes(action)) return false
    if (stage && !m.stages.includes(stage)) return false
    return true
  }

  function applyTokens(pair: TokenPair) {
    tokenStore.save(pair)
  }

  async function login(username: string, password: string) {
    const pair = await authApi.login({ username, password })
    tokenStore.save(pair)
    await fetchMe()
  }

  async function fetchMe() {
    loading.value = true
    try {
      user.value = await authApi.me()
    } finally {
      loading.value = false
    }
    return user.value
  }

  function logout() {
    tokenStore.clear()
    user.value = null
  }

  return {
    user,
    loading,
    isLoggedIn,
    myProjectIds,
    managedOrgs,
    isUnitAdmin,
    canManageStaff,
    mustChangePassword,
    membershipOf,
    unitIn,
    visibleStages,
    primaryStages,
    isPrimaryOf,
    can,
    applyTokens,
    login,
    fetchMe,
    logout,
  }
})
