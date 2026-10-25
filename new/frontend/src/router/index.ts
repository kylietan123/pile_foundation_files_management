/** 路由与登录守卫。 */
import { createRouter, createWebHashHistory, type RouteRecordRaw } from 'vue-router'

import { tokenStore } from '@/api/http'
import { useAuthStore } from '@/stores/auth'

const routes: RouteRecordRaw[] = [
  {
    path: '/login',
    name: 'login',
    component: () => import('@/views/LoginView.vue'),
    meta: { public: true, title: '登录' },
  },
  {
    path: '/change-initial-password',
    name: 'change-initial-password',
    component: () => import('@/views/ForcePasswordChangeView.vue'),
    meta: { title: '首次修改密码' },
  },
  {
    path: '/',
    component: () => import('@/layouts/MainLayout.vue'),
    children: [
      {
        path: '',
        redirect: () => {
          const auth = useAuthStore()
          if (auth.mustChangePassword) return { name: 'change-initial-password' }
          return auth.user?.is_superuser ? { name: 'admin' } : { name: 'projects' }
        },
      },
      {
        path: 'profile',
        name: 'profile',
        component: () => import('@/views/ProfileView.vue'),
        meta: { title: '个人设置' },
      },
      {
        path: 'admin',
        name: 'admin',
        component: () => import('@/views/AdminConsoleView.vue'),
        meta: { title: '权限管理', adminOnly: true },
      },
      {
        path: 'projects',
        name: 'projects',
        component: () => import('@/views/ProjectListView.vue'),
        meta: { title: '工作台' },
      },
      {
        path: 'projects/:id',
        name: 'project-detail',
        component: () => import('@/views/ProjectDetailView.vue'),
        meta: { title: '项目总览' },
      },
      {
        path: 'projects/:id/design-inputs',
        name: 'design-inputs',
        component: () => import('@/views/DesignInputView.vue'),
        meta: { title: '设计输入管理' },
      },
      {
        path: 'projects/:id/documents',
        name: 'documents',
        component: () => import('@/views/DocumentsView.vue'),
        meta: { title: '文件与版本' },
      },
      {
        path: 'projects/:id/changes',
        name: 'changes',
        component: () => import('@/views/ChangesView.vue'),
        meta: { title: '设计变更' },
      },
      {
        path: 'projects/:id/issues',
        name: 'issues',
        component: () => import('@/views/IssuesView.vue'),
        meta: { title: '问题管理' },
      },
      {
        path: 'projects/:id/deliverables',
        name: 'deliverables',
        component: () => import('@/views/DeliverablesView.vue'),
        meta: { title: '设计成果与交付' },
      },
      {
        path: 'projects/:id/ledger',
        name: 'ledger',
        component: () => import('@/views/LedgerView.vue'),
        meta: { title: '文件台账与追溯' },
      },
      {
        path: 'knowledge',
        name: 'knowledge',
        component: () => import('@/views/KnowledgeView.vue'),
        meta: { title: '知识库' },
      },
      {
        path: 'ai',
        name: 'ai',
        component: () => import('@/views/AIChatView.vue'),
        meta: { title: 'AI 助手' },
      },
      {
        path: 'my-work',
        name: 'my-work',
        component: () => import('@/views/WorkbenchView.vue'),
        meta: { title: '我的工作' },
      },
    ],
  },
  {
    path: '/:pathMatch(.*)*',
    redirect: '/projects',
  },
]

export const router = createRouter({
  history: createWebHashHistory(),
  routes,
})

router.beforeEach(async (to) => {
  const auth = useAuthStore()

  if (to.meta.public) {
    if (auth.isLoggedIn) {
      if (auth.mustChangePassword) return { name: 'change-initial-password' }
      return auth.user?.is_superuser ? { name: 'admin' } : { name: 'projects' }
    }
    return true
  }

  if (!tokenStore.access) {
    return { name: 'login', query: { redirect: to.fullPath } }
  }

  // 有 token 但还没拉过用户信息（例如刷新页面）→ 补拉
  if (!auth.user) {
    try {
      await auth.fetchMe()
    } catch {
      auth.logout()
      return { name: 'login', query: { redirect: to.fullPath } }
    }
  }
  if (auth.mustChangePassword && to.name !== 'change-initial-password') {
    return { name: 'change-initial-password' }
  }
  if (!auth.mustChangePassword && to.name === 'change-initial-password') {
    return auth.user?.is_superuser ? { name: 'admin' } : { name: 'projects' }
  }
  if (to.meta.adminOnly && !auth.canManageStaff) {
    return { name: 'projects' }
  }
  return true
})

router.afterEach((to) => {
  const t = to.meta.title as string | undefined
  document.title = t ? `${t} · 桩基工程全过程管理文档平台` : '桩基工程全过程管理文档平台'
})

export default router
