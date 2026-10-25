<script setup lang="ts">
/** 个人设置：查看账号与项目身份，修改资料和登录密码。 */
import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'

import { authApi } from '@/api'
import { explainApiError } from '@/api/http'
import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()
const savingProfile = ref(false)
const savingPassword = ref(false)

const profileForm = reactive({
  phone: '',
  email: '',
})

const passwordForm = reactive({
  old_password: '',
  new_password: '',
  confirm_password: '',
})

onMounted(async () => {
  if (!auth.user) await auth.fetchMe()
  resetProfileForm()
})

function resetProfileForm() {
  Object.assign(profileForm, {
    phone: auth.user?.phone || '',
    email: auth.user?.email || '',
  })
}

async function saveProfile() {
  savingProfile.value = true
  try {
    await authApi.updateMe({
      phone: profileForm.phone || null,
      email: profileForm.email || null,
    })
    await auth.fetchMe()
    resetProfileForm()
    ElMessage.success('个人资料已保存')
  } catch (e) {
    ElMessage.error(explainApiError(e))
  } finally {
    savingProfile.value = false
  }
}

async function changePassword() {
  if (!passwordForm.old_password || !passwordForm.new_password) {
    ElMessage.warning('请填写完整密码信息')
    return
  }
  if (passwordForm.new_password.length < 6) {
    ElMessage.warning('新密码至少 6 位')
    return
  }
  if (passwordForm.new_password !== passwordForm.confirm_password) {
    ElMessage.warning('两次输入的新密码不一致')
    return
  }
  savingPassword.value = true
  try {
    const result = await authApi.changePassword({
      old_password: passwordForm.old_password,
      new_password: passwordForm.new_password,
    })
    auth.applyTokens(result)
    await auth.fetchMe()
    Object.assign(passwordForm, { old_password: '', new_password: '', confirm_password: '' })
    ElMessage.success(result.message || '登录密码已修改')
  } catch (e) {
    ElMessage.error(explainApiError(e))
  } finally {
    savingPassword.value = false
  }
}
</script>

<template>
  <div class="profile-page">
    <header class="profile-head">
      <div>
        <div class="eyebrow">PERSONAL SETTINGS</div>
        <h2>个人设置</h2>
        <p>查看个人账号和所属单位，维护联系方式与登录密码。</p>
      </div>
    </header>

    <div class="profile-grid">
      <section class="app-card setting-card">
        <div class="card-title">个人信息与联系方式</div>
        <p class="hint">姓名、职称和工号由系统管理员统一维护，员工本人不可修改。</p>
        <el-form label-position="top" :model="profileForm">
          <div class="form-grid">
            <el-form-item label="姓名">
              <el-input :model-value="auth.user?.name" disabled />
            </el-form-item>
            <el-form-item label="职称">
              <el-input :model-value="auth.user?.title || '未设置'" disabled />
            </el-form-item>
            <el-form-item label="工号">
              <el-input :model-value="auth.user?.employee_no || '未设置'" disabled />
            </el-form-item>
            <el-form-item label="所属单位">
              <el-input :model-value="auth.user?.orgs?.map((o) => o.name).join('、') || '未设置'" disabled />
            </el-form-item>
            <el-form-item label="手机">
              <el-input v-model="profileForm.phone" />
            </el-form-item>
            <el-form-item label="邮箱">
              <el-input v-model="profileForm.email" />
            </el-form-item>
          </div>
        </el-form>
        <div class="actions">
          <el-button @click="resetProfileForm">还原</el-button>
          <el-button type="primary" :loading="savingProfile" @click="saveProfile">保存资料</el-button>
        </div>
      </section>

      <section class="app-card setting-card password-card">
        <div class="card-title">修改登录密码</div>
        <p class="hint">修改后其他设备会退出登录，当前设备会继续使用新会话。</p>
        <el-form label-position="top" :model="passwordForm">
          <el-form-item label="原密码">
            <el-input v-model="passwordForm.old_password" type="password" show-password />
          </el-form-item>
          <el-form-item label="新密码">
            <el-input v-model="passwordForm.new_password" type="password" show-password />
          </el-form-item>
          <el-form-item label="确认新密码">
            <el-input v-model="passwordForm.confirm_password" type="password" show-password />
          </el-form-item>
        </el-form>
        <div class="actions">
          <el-button type="primary" :loading="savingPassword" @click="changePassword">
            修改密码
          </el-button>
        </div>
      </section>

    </div>
  </div>
</template>

<style scoped>
.profile-page {
  max-width: 1180px;
  margin: 0 auto;
}

.profile-head {
  margin-bottom: 18px;
}

.eyebrow {
  color: #1a6bb0;
  font-size: 10.5px;
  font-weight: 800;
  letter-spacing: 2px;
}

.profile-head h2 {
  margin: 3px 0;
  color: #1f2a3d;
  font-size: 26px;
}

.profile-head p {
  margin: 0;
  color: #6b7688;
  font-size: 13px;
}

.profile-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.15fr) minmax(360px, 0.85fr);
  align-items: stretch;
  gap: 16px;
}

.setting-card {
  padding: 22px;
}

.card-title {
  margin-bottom: 15px;
  color: #1f2a3d;
  font-size: 16px;
  font-weight: 700;
}

.form-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  column-gap: 14px;
}

:deep(.el-input.is-disabled .el-input__wrapper) {
  background: #f3f5f8;
  box-shadow: 0 0 0 1px #e3e8f0 inset;
}

.actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}

.hint {
  margin: -8px 0 14px;
  color: #8793a5;
  font-size: 12px;
}

@media (max-width: 900px) {
  .profile-grid {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 720px) {
  .form-grid {
    grid-template-columns: 1fr;
  }
}
</style>
