/** 项目状态。首页项目列表的数据源。 */
import { defineStore } from 'pinia'
import { ref } from 'vue'

import { projectApi } from '@/api'
import { explainApiError } from '@/api/http'
import type { ProjectInfo } from '@/api/types'

export const useProjectStore = defineStore('project', () => {
  const projects = ref<ProjectInfo[]>([])
  const current = ref<ProjectInfo | null>(null)
  const loading = ref(false)
  const error = ref<string | null>(null)

  /** 拉取"我的项目"。后端已按权限过滤。 */
  async function fetchMyProjects(params?: { status?: string; keyword?: string }) {
    loading.value = true
    error.value = null
    try {
      projects.value = await projectApi.list(params)
    } catch (e) {
      error.value = explainApiError(e)
      projects.value = []
    } finally {
      loading.value = false
    }
    return projects.value
  }

  async function fetchDetail(id: string) {
    loading.value = true
    error.value = null
    try {
      current.value = await projectApi.detail(id)
    } catch (e) {
      error.value = explainApiError(e)
      current.value = null
    } finally {
      loading.value = false
    }
    return current.value
  }

  /** 首页汇总：跨项目待办与风险。一人多项目场景下的刚需。 */
  function summary() {
    const list = projects.value
    return {
      total: list.length,
      inProgress: list.filter((p) => p.status === 'IN_PROGRESS').length,
      archived: list.filter((p) => p.status === 'ARCHIVED').length,
      pendingTasks: list.reduce((s, p) => s + p.pending_task_count, 0),
      overdue: list.reduce((s, p) => s + p.overdue_count, 0),
      openIssues: list.reduce((s, p) => s + p.open_issue_count, 0),
    }
  }

  return { projects, current, loading, error, fetchMyProjects, fetchDetail, summary }
})
