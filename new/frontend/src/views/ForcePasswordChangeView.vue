<script setup lang="ts">
/** 首次登录 / 管理员重置密码后，强制修改密码。 */
import { computed, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'

import { authApi } from '@/api'
import { explainApiError } from '@/api/http'
import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()
const router = useRouter()
const saving = ref(false)
const form = reactive({
  old_password: '',
  new_password: '',
  confirm_password: '',
})

const displayName = computed(() => auth.user?.name || auth.user?.username || '')

async function submit() {
  if (!form.old_password || !form.new_password) {
    ElMessage.warning('请填写原密码和新密码')
    return
  }
  if (form.new_password.length < 6) {
    ElMessage.warning('新密码至少 6 位')
    return
  }
  if (form.new_password !== form.confirm_password) {
    ElMessage.warning('两次输入的新密码不一致')
    return
  }
  saving.value = true
  try {
    const result = await authApi.changePassword({
      old_password: form.old_password,
      new_password: form.new_password,
    })
    auth.applyTokens(result)
    await auth.fetchMe()
    ElMessage.success('密码已修改，正在进入系统')
    router.push(auth.user?.is_superuser ? { name: 'admin' } : { name: 'projects' })
  } catch (e) {
    ElMessage.error(explainApiError(e))
  } finally {
    saving.value = false
  }
}

function logout() {
  auth.logout()
  router.push({ name: 'login' })
}
</script>

<template>
  <main class="force-page">
    <section class="force-card">
      <div class="eyebrow">FIRST LOGIN SECURITY</div>
      <h1>请先修改初始密码</h1>
      <p class="intro">
        {{ displayName }}，你的账号当前处于“首次登录/密码已重置”状态。完成修改后才能进入系统。
      </p>

      <el-alert
        type="warning"
        :closable="false"
        show-icon
        title="初始密码只用于第一次登录或管理员重置后登录，请设置自己的新密码。"
        class="notice"
      />

      <el-form label-position="top" :model="form">
        <el-form-item label="当前密码">
          <el-input v-model="form.old_password" type="password" show-password autocomplete="current-password" />
        </el-form-item>
        <el-form-item label="新密码">
          <el-input v-model="form.new_password" type="password" show-password autocomplete="new-password" />
        </el-form-item>
        <el-form-item label="确认新密码">
          <el-input v-model="form.confirm_password" type="password" show-password autocomplete="new-password" />
        </el-form-item>
      </el-form>

      <el-button type="primary" class="submit" :loading="saving" @click="submit">
        修改密码并进入系统
      </el-button>
      <el-button link class="logout" @click="logout">退出登录</el-button>
    </section>
  </main>
</template>

<style scoped>
.force-page {
  min-height: 100vh;
  display: grid;
  place-items: center;
  padding: 24px;
  background:
    radial-gradient(circle at 15% 15%, rgba(77, 163, 255, 0.22), transparent 34%),
    linear-gradient(135deg, #0d2a4d, #155e91 55%, #0f8f8a);
}

.force-card {
  width: min(440px, 100%);
  padding: 30px 32px 24px;
  border-radius: 14px;
  background: #fff;
  box-shadow: 0 22px 60px rgba(7, 30, 56, 0.3);
}

.eyebrow {
  color: #1a6bb0;
  font-size: 10.5px;
  font-weight: 800;
  letter-spacing: 2px;
}

h1 {
  margin: 6px 0 8px;
  color: #1f2a3d;
  font-size: 25px;
}

.intro {
  margin: 0 0 16px;
  color: #6b7688;
  font-size: 13px;
  line-height: 1.7;
}

.notice {
  margin-bottom: 18px;
}

.submit {
  width: 100%;
  height: 42px;
  margin-top: 2px;
}

.logout {
  display: block;
  margin: 14px auto 0;
}
</style>
