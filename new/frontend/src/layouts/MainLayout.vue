<script setup lang="ts">
/**
 * 主布局：顶栏 + 内容区。
 *
 * 注意：**7 个阶段不在这一层**。
 * 阶段属于项目，是「项目内导航」，放在 ProjectDetailView 里。
 * 这是刻意设计 —— 一人多项目场景下，首页必须是项目列表。
 */
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'

import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()
const route = useRoute()
const router = useRouter()

const navItems = [
  { name: 'projects', label: '工作台', to: { name: 'projects' } },
  { name: 'my-work', label: '我的工作', to: { name: 'my-work' } },
  { name: 'knowledge', label: '知识库', to: { name: 'knowledge' } },
  { name: 'ai', label: 'AI 助手', to: { name: 'ai' } },
]

const activeNav = computed(() => {
  const n = route.name as string
  // 项目内的各页都归到「项目」这个一级导航
  if (
    [
      'project-detail',
      'design-inputs',
      'documents',
      'changes',
      'issues',
      'deliverables',
      'ledger',
    ].includes(n)
  ) {
    return 'projects'
  }
  return n
})

const primaryOrg = computed(() => auth.user?.orgs?.[0]?.name ?? '')
// 顶栏显示"我以哪些单位参与" —— 一个人可能在不同项目里代表不同单位
const roleSummary = computed(() => {
  const ms = auth.user?.memberships ?? []
  const units = Array.from(new Set(ms.map((m) => m.unit_label)))
  return units.length ? units.join(' / ') : '—'
})

function onNav(item: (typeof navItems)[number]) {
  if (!item.to) {
    ElMessage.info(`「${item.label}」将在后续迭代中实现`)
    return
  }
  router.push(item.to)
}

function logout() {
  auth.logout()
  router.push({ name: 'login' })
}
</script>

<template>
  <div class="layout">
    <!-- 顶栏 -->
    <header class="topbar">
      <div class="brand">桩基工程全过程管理文档平台</div>
      <nav class="topnav">
        <span
          v-for="item in navItems"
          :key="item.name"
          :class="{ on: activeNav === item.name, placeholder: !item.to }"
          @click="onNav(item)"
        >
          {{ item.label }}
        </span>
      </nav>
      <div class="topright">
        <span class="org">{{ primaryOrg }}</span>
        <el-dropdown trigger="click">
          <span class="user">
            <span class="avatar">{{ auth.user?.name?.charAt(0) ?? '?' }}</span>
            <span>{{ auth.user?.name }}</span>
            <el-icon><ArrowDown /></el-icon>
          </span>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item disabled>
                角色：{{ roleSummary }}
              </el-dropdown-item>
              <el-dropdown-item disabled>
                参与项目 {{ auth.user?.memberships.length ?? 0 }} 个
              </el-dropdown-item>
              <el-dropdown-item divided @click="logout">退出登录</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
      </div>
    </header>

    <!-- 内容 -->
    <main class="content">
      <router-view />
    </main>
  </div>
</template>

<style scoped>
.layout {
  min-height: 100%;
  display: flex;
  flex-direction: column;
}

.topbar {
  height: 56px;
  background: var(--navy);
  color: #fff;
  display: flex;
  align-items: center;
  padding: 0 26px;
  gap: 34px;
  flex: 0 0 auto;
}

.brand {
  font-size: 17px;
  font-weight: 700;
  letter-spacing: 0.5px;
  white-space: nowrap;
}

.topnav {
  display: flex;
  gap: 26px;
  font-size: 14px;
  color: #c4d6ea;
}
.topnav span {
  cursor: pointer;
  padding-bottom: 2px;
  border-bottom: 2px solid transparent;
  user-select: none;
}
.topnav span:hover {
  color: #fff;
}
.topnav span.on {
  color: #fff;
  font-weight: 700;
  border-bottom-color: #4da3ff;
}
.topnav span.placeholder {
  color: #7d93ab;
}

.topright {
  margin-left: auto;
  display: flex;
  align-items: center;
  gap: 18px;
  font-size: 13px;
  color: #c4d6ea;
}
.org {
  opacity: 0.85;
}
.user {
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
  color: #fff;
  outline: none;
}
.avatar {
  width: 28px;
  height: 28px;
  border-radius: 50%;
  background: #4da3ff;
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  font-weight: 700;
  flex: 0 0 auto;
}

.content {
  flex: 1 1 auto;
  padding: 20px 26px 30px;
  overflow: auto;
}
</style>
