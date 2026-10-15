<script setup lang="ts">
/**
 * 登录页。
 *
 * 演示账号直接列在页面上 —— 内部试用阶段方便评委/设计院同事登录体验。
 * 正式部署前必须去掉（在 README 里已标注）。
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

const form = reactive({
  username: '',
  password: '',
})

const rules: FormRules = {
  username: [{ required: true, message: '请输入用户名', trigger: 'blur' }],
  password: [{ required: true, message: '请输入密码', trigger: 'blur' }],
}

/**
 * 演示账号：点击即填充。
 *
 * 覆盖不同参与单位，便于对比权限差异。
 * **正式部署前必须移除这一段**（README 已列为上线前必做项）。
 */
const demos = [
  { username: 'ouyuxin', name: '欧雨欣', desc: '设计单位（设计阶段主办）' },
  { username: 'chenkaili', name: '陈铠俐', desc: '建设单位（前期调研主办）' },
  { username: 'ligong', name: '李工', desc: '勘察单位（勘察主办）' },
  { username: 'sunqi', name: '孙七', desc: '总包单位（施工主办）' },
  { username: 'wangwu', name: '王五', desc: '监理单位（只能签意见）' },
  { username: 'gongwu', name: '龚武', desc: '政府审查单位（只读）' },
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
    const redirect = (route.query.redirect as string) || '/projects'
    router.push(redirect)
  } catch (e) {
    ElMessage.error(explainApiError(e))
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="login-page">
    <!-- 左侧品牌区 -->
    <div class="brand-side">
      <div class="brand-inner">
        <h1>桩基工程<br />全生命周期管理平台</h1>
        <p class="sub">
          面向设计院内部试用的多项目、多参与单位、多阶段工程文档与设计协同平台
        </p>

        <div class="stages">
          <div v-for="(s, i) in ['前期调研', '勘察', '设计试桩', '设计', '施工', '验收试桩', '运维监测']" :key="s" class="st">
            <span class="n">{{ String(i + 1).padStart(2, '0') }}</span>
            <span class="t">{{ s }}</span>
          </div>
        </div>

        <ul class="features">
          <li>文件版本状态机 —— 未发布版本不可被下游引用</li>
          <li>角色 × 数据范围 × 阶段 三层权限，一份配置全局生效</li>
          <li>设计参数全链路溯源 —— 每个参数可回溯到勘察报告页码</li>
          <li>AI 输出强制带引用与不确定性说明，不替代设计人签字</li>
        </ul>
      </div>
    </div>

    <!-- 右侧登录表单 -->
    <div class="form-side">
      <div class="form-box">
        <h2>登录</h2>
        <p class="tip">请使用院内账号登录</p>

        <el-form ref="formRef" :model="form" :rules="rules" size="large" @keyup.enter="onSubmit">
          <el-form-item prop="username">
            <el-input v-model="form.username" placeholder="用户名" clearable>
              <template #prefix><el-icon><User /></el-icon></template>
            </el-input>
          </el-form-item>
          <el-form-item prop="password">
            <el-input v-model="form.password" type="password" placeholder="密码" show-password>
              <template #prefix><el-icon><Lock /></el-icon></template>
            </el-input>
          </el-form-item>
          <el-form-item>
            <el-button type="primary" :loading="loading" style="width: 100%" @click="onSubmit">
              登 录
            </el-button>
          </el-form-item>
        </el-form>

        <el-divider>
          <span class="t-grey t-sm">演示账号（点击填充，密码 Tjad@2026）</span>
        </el-divider>

        <div class="demos">
          <div v-for="d in demos" :key="d.username" class="demo" @click="fill(d.username)">
            <div class="dn">{{ d.name }}</div>
            <div class="dd">{{ d.desc }}</div>
            <div class="du t-mono">{{ d.username }}</div>
          </div>
        </div>

        <p class="warn">
          注意：正式部署前必须移除本页的演示账号列表。
        </p>
      </div>
    </div>
  </div>
</template>

<style scoped>
.login-page {
  display: grid;
  grid-template-columns: 1.05fr 1fr;
  min-height: 100vh;
}

/* ---------------- 左侧 ---------------- */
.brand-side {
  background: linear-gradient(150deg, #0d2344 0%, #12305c 45%, #1c4a86 100%);
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 60px 56px;
}
.brand-inner {
  max-width: 480px;
}
.brand-side h1 {
  font-size: 32px;
  line-height: 1.35;
  margin: 0 0 16px;
  font-weight: 700;
  letter-spacing: 1px;
}
.sub {
  color: #a9c6e6;
  font-size: 13.5px;
  line-height: 1.7;
  margin: 0 0 30px;
}

.stages {
  display: flex;
  flex-wrap: wrap;
  gap: 7px;
  margin-bottom: 30px;
}
.st {
  background: rgba(255, 255, 255, 0.1);
  border: 1px solid rgba(255, 255, 255, 0.16);
  border-radius: 3px;
  padding: 5px 10px;
  font-size: 12px;
  display: flex;
  align-items: center;
  gap: 6px;
}
.st .n {
  color: #7fc4ff;
  font-size: 10.5px;
  font-weight: 700;
}

.features {
  list-style: none;
  padding: 0;
  margin: 0;
  font-size: 12.5px;
  color: #c4d6ea;
  line-height: 2;
}
.features li {
  padding-left: 16px;
  position: relative;
}
.features li::before {
  content: '';
  position: absolute;
  left: 0;
  top: 10px;
  width: 5px;
  height: 5px;
  border-radius: 1px;
  background: #4da3ff;
}

/* ---------------- 右侧 ---------------- */
.form-side {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 40px 32px;
  background: #fff;
  overflow: auto;
}
.form-box {
  width: 100%;
  max-width: 390px;
}
.form-box h2 {
  margin: 0 0 6px;
  font-size: 24px;
  font-weight: 700;
}
.tip {
  color: var(--grey);
  font-size: 13px;
  margin: 0 0 26px;
}

.demos {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
}
.demo {
  border: 1px solid var(--line);
  border-radius: 5px;
  padding: 9px 11px;
  cursor: pointer;
  transition: all 0.15s;
  background: #fbfcfe;
}
.demo:hover {
  border-color: var(--blue);
  background: var(--blue-soft);
}
.dn {
  font-size: 13px;
  font-weight: 700;
  color: var(--ink);
}
.dd {
  font-size: 11px;
  color: var(--grey);
  margin: 1px 0 3px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.du {
  font-size: 11px;
  color: var(--blue);
}

.warn {
  margin: 18px 0 0;
  font-size: 11.5px;
  color: var(--amber);
  background: var(--amber-soft);
  border: 1px solid #f0dcb0;
  border-radius: 4px;
  padding: 7px 11px;
}

@media (max-width: 1100px) {
  .login-page {
    grid-template-columns: 1fr;
  }
  .brand-side {
    display: none;
  }
}
</style>
