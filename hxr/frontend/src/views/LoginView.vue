<script setup lang="ts">
/**
 * 合并版登录页。
 *
 * 视觉与交互采用 hxr 版的单卡片登录：品牌区置顶、演示账号一键填充、
 * 表单聚焦，不改变 oyx 后端的 JWT 认证契约。
 */
import { reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, type FormInstance, type FormRules } from 'element-plus'

import { explainApiError } from '@/api/http'
import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()
const router = useRouter()
const route = useRoute()

const formRef = ref<FormInstance>()
const loading = ref(false)
const form = reactive({ username: '', password: '' })

const rules: FormRules = {
  username: [{ required: true, message: '请输入用户名', trigger: 'blur' }],
  password: [{ required: true, message: '请输入密码', trigger: 'blur' }],
}

const demos = [
  { username: 'ouyuxin', name: '欧雨欣', desc: '设计单位' },
  { username: 'chenkaili', name: '陈铠俐', desc: '建设单位' },
  { username: 'haoxirui', name: '郝兮睿', desc: '勘察 / 设计试桩' },
  { username: 'sunqi', name: '孙七', desc: '总包单位' },
  { username: 'wangwu', name: '王五', desc: '监理单位' },
  { username: 'admin', name: '系统管理员', desc: '全局查看' },
]

function fill(username: string) {
  form.username = username
  form.password = 'Tjad@2026'
}

async function onSubmit() {
  if (!formRef.value) return
  const ok = await formRef.value.validate().catch(() => false)
  if (!ok) return

  loading.value = true
  try {
    await auth.login(form.username, form.password)
    ElMessage.success(`欢迎，${auth.user?.name}`)
    router.push((route.query.redirect as string) || '/projects')
  } catch (e) {
    ElMessage.error(explainApiError(e))
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <main class="login-page">
    <section class="login-card">
      <div class="login-brand">
        <div class="brand-mark">桩</div>
        <h1>桩基工程全过程管理文档平台</h1>
        <p>全过程 · 全阶段 · 全文档</p>
      </div>

      <div class="stage-ribbon">
        <span v-for="(stage, index) in ['调研', '勘察', '设计试桩', '设计', '施工', '验收', '运维']" :key="stage">
          <b>{{ String(index + 1).padStart(2, '0') }}</b>{{ stage }}
        </span>
      </div>

      <el-form ref="formRef" :model="form" :rules="rules" size="large" @keyup.enter="onSubmit">
        <el-form-item prop="username">
          <el-input v-model="form.username" placeholder="用户名（姓名拼音）" clearable>
            <template #prefix><el-icon><User /></el-icon></template>
          </el-input>
        </el-form-item>
        <el-form-item prop="password">
          <el-input v-model="form.password" type="password" placeholder="密码" show-password>
            <template #prefix><el-icon><Lock /></el-icon></template>
          </el-input>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :loading="loading" class="login-button" @click="onSubmit">
            登 录
          </el-button>
        </el-form-item>
      </el-form>

      <div class="demo-title">
        <span>演示账号</span>
        <small>点击填充 · 统一密码 Tjad@2026</small>
      </div>
      <div class="demos">
        <button v-for="d in demos" :key="d.username" type="button" class="demo" @click="fill(d.username)">
          <b>{{ d.name }}</b>
          <span>{{ d.desc }}</span>
          <small>{{ d.username }}</small>
        </button>
      </div>

      <p class="security-note">登录后仅显示你所在单位有权限查看的项目与阶段。</p>
    </section>
  </main>
</template>

<style scoped>
.login-page {
  min-height: 100vh;
  display: grid;
  place-items: center;
  padding: 30px 18px;
  background:
    radial-gradient(circle at 15% 12%, rgba(14, 165, 164, 0.32), transparent 31%),
    linear-gradient(135deg, #0f4f8a 0%, #1a6bb0 55%, #0ea5a4 100%);
}

.login-card {
  width: min(460px, 100%);
  padding: 34px 36px 30px;
  border-radius: 18px;
  background: rgba(255, 255, 255, 0.98);
  box-shadow: 0 24px 70px rgba(3, 25, 52, 0.3);
}

.login-brand {
  text-align: center;
  margin-bottom: 22px;
}

.brand-mark {
  width: 62px;
  height: 62px;
  line-height: 62px;
  margin: 0 auto 13px;
  border-radius: 16px;
  color: #fff;
  font-size: 30px;
  font-weight: 800;
  background: linear-gradient(135deg, #1a6bb0, #0ea5a4);
  box-shadow: 0 8px 20px rgba(26, 107, 176, 0.34);
}

h1 {
  margin: 0;
  color: #1f2a3d;
  font-size: 20px;
  line-height: 1.35;
}

.login-brand p {
  margin: 5px 0 0;
  color: #6b7688;
  font-size: 12.5px;
  letter-spacing: 2px;
}

.stage-ribbon {
  display: flex;
  gap: 4px;
  justify-content: center;
  margin: 0 0 21px;
}

.stage-ribbon span {
  display: flex;
  gap: 3px;
  align-items: baseline;
  padding: 4px 6px;
  border-radius: 5px;
  background: #eef4fa;
  color: #47617d;
  font-size: 10.5px;
  white-space: nowrap;
}

.stage-ribbon b {
  color: #1a6bb0;
  font-size: 9px;
}

.login-button {
  width: 100%;
  height: 42px;
  font-weight: 700;
  letter-spacing: 3px;
}

.demo-title {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  margin: 16px 0 8px;
  color: #1f2a3d;
  font-size: 13px;
  font-weight: 700;
}

.demo-title small {
  color: #8793a5;
  font-size: 11px;
  font-weight: 400;
}

.demos {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 7px;
}

.demo {
  display: grid;
  grid-template-columns: 1fr auto;
  gap: 1px 8px;
  padding: 8px 10px;
  border: 1px solid #e3e8f0;
  border-radius: 8px;
  background: #fff;
  text-align: left;
  cursor: pointer;
  transition: 0.15s ease;
}

.demo:hover {
  border-color: #1a6bb0;
  background: #f4f9ff;
  transform: translateY(-1px);
}

.demo b {
  color: #27364d;
  font-size: 12.5px;
}

.demo span,
.demo small {
  color: #7a8799;
  font-size: 10.5px;
}

.demo small {
  grid-column: 1 / -1;
  font-family: Consolas, 'Courier New', monospace;
}

.security-note {
  margin: 15px 0 0;
  color: #8793a5;
  font-size: 11.5px;
  text-align: center;
}

@media (max-width: 520px) {
  .login-card {
    padding: 28px 20px 24px;
  }
  .stage-ribbon {
    display: none;
  }
}
</style>
