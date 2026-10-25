<script setup lang="ts">
/**
 * 设计成果与交付。
 *
 * **这是设计阶段最需要"站得住"的环节。**
 *
 * 设计文件一旦交付给施工方，图纸版本出错就是责任问题。
 * 所以"能不能交付"不能靠人记得检查，必须由系统逐项校验六道关卡：
 *
 *   1 设计输入已锁定   —— 否则设计依据可以被悄悄改掉
 *   2 参数来源有效     —— 否则用了过期勘察数据
 *   3 成果齐备         —— 否则交付物缺项
 *   4 版本有效         —— 否则下游引用未发布版本
 *   5 问题闭环         —— 否则已知问题被带进施工
 *   6 变更闭环         —— 否则批了没改，图纸与现场不一致
 *
 * 第 1、2 关是这套系统区别于通用文档管理系统的关键：
 * 通用系统只检查"文件在不在"，我们检查"设计依据站不站得住"。
 */
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import StageContextBar from '@/components/StageContextBar.vue'
import { ElMessage } from 'element-plus'

import { deliverableApi } from '@/api'
import { explainApiError } from '@/api/http'
import type { Deliverable, DeliveryCheck, DeliveryGate, Manifest } from '@/api/types'
import { DOCUMENT_STATE_LABEL, DocumentState } from '@/api/types'
import { useAuthStore } from '@/stores/auth'
import { formatDate, formatDateTime } from '@/utils/format'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const projectId = computed(() => route.params.id as string)
const stage = computed(() => (route.query.stage as string) || null)

const loading = ref(false)
const error = ref<string | null>(null)
const deliverables = ref<Deliverable[]>([])
const check = ref<DeliveryCheck | null>(null)
const toast = ref<string | null>(null)

/** 交付清单抽屉 */
const manifestOpen = ref(false)
const manifest = ref<Manifest | null>(null)
const manifestLoading = ref(false)

const canEdit = computed(() => !!auth.membershipOf(projectId.value))

async function load() {
  loading.value = true
  error.value = null
  try {
    const [dels, chk] = await Promise.all([
      deliverableApi.list(projectId.value, stage.value || undefined),
      deliverableApi.check(projectId.value, stage.value || undefined),
    ])
    deliverables.value = dels
    check.value = chk.data
    toast.value = chk.message
  } catch (e) {
    error.value = explainApiError(e)
  } finally {
    loading.value = false
  }
}

onMounted(load)
watch(stage, load)

/** ---------------- 交付清单 ---------------- */

async function openManifest() {
  manifestOpen.value = true
  manifestLoading.value = true
  try {
    manifest.value = await deliverableApi.manifest(projectId.value)
  } catch (e) {
    ElMessage.error(explainApiError(e))
    manifest.value = null
  } finally {
    manifestLoading.value = false
  }
}

/** ---------------- 展示辅助 ---------------- */

/** 关卡图标 */
function gateIcon(g: DeliveryGate): string {
  return g.passed ? '✓' : '✕'
}

/** 成果状态标签 */
function deliverableTag(d: Deliverable): {
  type: 'success' | 'info' | 'warning' | 'danger'
  text: string
} {
  if (!d.exists) return { type: 'danger', text: '缺失' }
  if (d.ready) return { type: 'success', text: '就绪' }
  if (!d.current_version_no) return { type: 'warning', text: '无有效版本' }
  return { type: 'warning', text: '版本未就绪' }
}

const requiredCount = computed(() => deliverables.value.filter((d) => d.required).length)
const readyCount = computed(
  () => deliverables.value.filter((d) => d.required && d.ready).length,
)

/** 跳转到对应处理页面 */
function gotoFix(g: DeliveryGate) {
  const map: Record<string, string> = {
    INPUTS_LOCKED: 'design-inputs',
    PARAM_SOURCE_VALID: 'design-inputs',
    DELIVERABLES_COMPLETE: 'documents',
    VERSIONS_PUBLISHED: 'documents',
    ISSUES_CLOSED: 'issues',
    CHANGES_CLOSED: 'changes',
  }
  const name = map[g.code]
  if (name) router.push({ name, params: { id: projectId.value } })
}

/** 状态标签（用于版本状态展示） */
const stateLabel = (s?: string | null) =>
  s ? DOCUMENT_STATE_LABEL[s as DocumentState] || s : '—'
</script>

<template>
  <div class="page">
    <StageContextBar :project-id="projectId" :stage="stage" active="deliverables" />
    <!-- 顶部 -->
    <div class="head app-card">
      <div class="head-l">
        <div class="sec-title" style="margin-bottom: 10px">
          设计成果与交付
          <span class="more" @click="router.push({ name: 'project-detail', params: { id: projectId } })">
            返回项目总览
          </span>
        </div>
        <p class="t-grey t-sm" style="margin: 0">
          交付前必须通过六道关卡。
          <b class="t-amber">不靠人记得检查，由系统逐项校验。</b>
          设计文件一旦交付，图纸版本出错就是责任问题。
        </p>
      </div>
      <div class="head-actions">
        <el-button size="small" @click="load">重新检查</el-button>
        <el-button size="small" type="primary" :disabled="!check?.can_deliver" @click="openManifest">
          生成交付清单
        </el-button>
      </div>
    </div>

    <el-skeleton v-if="loading" :rows="8" animated style="margin-top: 16px" />
    <el-alert v-else-if="error" :title="error" type="error" show-icon :closable="false" />

    <template v-else>
      <!-- 交付结论 -->
      <div
        class="verdict"
        :class="check?.can_deliver ? 'ok' : 'blocked'"
      >
        <div class="vd-icon">{{ check?.can_deliver ? '✓' : '!' }}</div>
        <div class="vd-body">
          <div class="vd-title">
            {{ check?.can_deliver ? '可以交付' : '暂不可交付' }}
          </div>
          <div class="vd-text">{{ toast || check?.summary }}</div>
        </div>
        <div class="vd-stat">
          <div class="vds">
            <span class="vds-num">{{ readyCount }}/{{ requiredCount }}</span>
            <span class="vds-lab">必交成果就绪</span>
          </div>
          <div class="vds">
            <span class="vds-num" :class="check?.failed_gate_count ? 't-red' : 't-teal'">
              {{ check ? 6 - check.failed_gate_count : 0 }}/6
            </span>
            <span class="vds-lab">关卡通过</span>
          </div>
        </div>
      </div>

      <!-- 六道关卡 -->
      <div class="app-card pad">
        <div class="sec-title">
          交付关卡
          <span class="more" style="cursor: default">
            {{ check ? 6 - check.failed_gate_count : 0 }}/6 通过
          </span>
        </div>

        <div class="gates">
          <div
            v-for="g in check?.gates || []"
            :key="g.code"
            class="gate"
            :class="{ passed: g.passed, failed: !g.passed }"
          >
            <div class="g-head">
              <div class="g-icon">{{ gateIcon(g) }}</div>
              <div class="g-title">
                <span class="g-num">关卡 {{ g.gate }}</span>
                {{ g.name }}
              </div>
              <el-tag :type="g.passed ? 'success' : 'danger'" size="small" effect="light">
                {{ g.passed ? '通过' : '未通过' }}
              </el-tag>
            </div>

            <div class="g-detail">{{ g.detail }}</div>

            <div v-if="!g.passed" class="g-blockers">
              <div v-for="(b, i) in g.blockers" :key="i" class="g-blocker">· {{ b }}</div>
              <div class="g-suggest">
                <b>怎么处理：</b>{{ g.suggestion }}
                <el-button
                  v-if="canEdit"
                  link
                  type="primary"
                  size="small"
                  @click="gotoFix(g)"
                >
                  去处理 →
                </el-button>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- 成果清单 -->
      <div class="app-card pad">
        <div class="sec-title">
          设计成果清单
          <span class="more" style="cursor: default">
            {{ deliverables.filter((d) => d.exists).length }}/{{ deliverables.length }} 项已有文件
          </span>
        </div>

        <el-table :data="deliverables" size="small" style="width: 100%">
          <el-table-column label="成果项" min-width="200">
            <template #default="{ row }">
              <span class="d-name">{{ row.type_name }}</span>
              <el-tag v-if="row.required" size="small" type="danger" effect="plain" class="req">
                必交
              </el-tag>
              <div v-if="row.note" class="t-grey t-sm">{{ row.note }}</div>
            </template>
          </el-table-column>

          <el-table-column label="文件" min-width="180">
            <template #default="{ row }">
              <template v-if="row.exists">
                <a
                  class="t-blue"
                  style="cursor: pointer"
                  @click="router.push({ name: 'documents', params: { id: projectId } })"
                >
                  {{ row.document_title }}
                </a>
                <div class="t-grey t-sm t-mono">{{ row.doc_no || '无编号' }}</div>
              </template>
              <span v-else class="t-grey t-sm">尚未创建</span>
            </template>
          </el-table-column>

          <el-table-column label="当前有效版本" width="150">
            <template #default="{ row }">
              <template v-if="row.current_version_no">
                <b class="t-teal">{{ row.current_version_no }}</b>
                <div class="t-grey t-sm">已发布</div>
              </template>
              <span v-else class="t-amber t-sm">无</span>
            </template>
          </el-table-column>

          <el-table-column label="版本情况" width="150">
            <template #default="{ row }">
              <span class="t-sm">共 {{ row.version_count }} 个版本</span>
              <div v-if="row.has_unpublished_newer" class="t-red t-sm">
                有在途版本 {{ row.latest_version_no }}
                （{{ stateLabel(row.latest_version_state) }}）
              </div>
            </template>
          </el-table-column>

          <el-table-column label="状态" width="110" align="center">
            <template #default="{ row }">
              <el-tag :type="deliverableTag(row).type" size="small" effect="light">
                {{ deliverableTag(row).text }}
              </el-tag>
            </template>
          </el-table-column>

          <el-table-column label="阻断原因" min-width="200">
            <template #default="{ row }">
              <div v-if="row.blockers.length" class="bl">
                <div v-for="(b, i) in row.blockers" :key="i" class="t-red t-sm">· {{ b }}</div>
              </div>
              <span v-else class="t-teal t-sm">✓ 可交付</span>
            </template>
          </el-table-column>
        </el-table>
      </div>

      <!-- 说明 -->
      <div class="rules">
        <b>为什么需要这六道关卡？</b>
        <ol>
          <li>
            <b>设计输入已锁定 / 参数来源有效</b> ——
            这两关是这套系统区别于通用文档管理系统的关键。
            通用系统只检查"文件在不在"，我们检查<b>设计依据站不站得住</b>：
            依据有没有被悄悄改动、是不是用了已经失效的勘察数据。
          </li>
          <li>
            <b>成果齐备 / 版本有效</b> ——
            交付物缺项、或下游引用了未发布版本，都会在现场造成返工。
          </li>
          <li>
            <b>问题闭环 / 变更闭环</b> ——
            已知问题被带进施工、或变更批了没改，是设计院最常见的责任风险。
          </li>
        </ol>
        <div style="margin-top: 8px">
          交付清单<b>只收录「已发布」版本的成果</b> ——
          未发布版本不可能出现在交付清单里，这是版本状态机的强制规则。
        </div>
      </div>
    </template>

    <!-- ============ 交付清单 ============ -->
    <el-drawer v-model="manifestOpen" title="交付清单" size="720px">
      <el-skeleton v-if="manifestLoading" :rows="6" animated />
      <template v-else-if="manifest">
        <el-alert type="info" :closable="false" show-icon style="margin-bottom: 14px">
          <template #title>
            {{ manifest.item_count }} 项成果
          </template>
          <div style="font-size: 12.5px; line-height: 1.7">{{ manifest.note }}</div>
        </el-alert>

        <el-table :data="manifest.items" size="small" style="width: 100%">
          <el-table-column prop="type_name" label="成果项" min-width="150" />
          <el-table-column prop="title" label="文件名称" min-width="180" />
          <el-table-column label="文件编号" width="130">
            <template #default="{ row }">
              <span class="t-mono t-sm">{{ row.doc_no || '—' }}</span>
            </template>
          </el-table-column>
          <el-table-column label="版本" width="90" align="center">
            <template #default="{ row }">
              <b class="t-teal">{{ row.version_no }}</b>
            </template>
          </el-table-column>
          <el-table-column label="发布日期" width="110">
            <template #default="{ row }">
              <span class="t-sm">{{ formatDate(row.published_at) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="标记" width="90" align="center">
            <template #default="{ row }">
              <el-tag v-if="row.is_self_checked" type="warning" size="small" effect="plain">
                自校
              </el-tag>
              <span v-else class="t-grey t-sm">—</span>
            </template>
          </el-table-column>
        </el-table>

        <div class="mf-foot">
          清单生成时间：{{ formatDateTime(manifest.generated_at) }}
        </div>
      </template>
    </el-drawer>
  </div>
</template>

<style scoped>
.page {
  max-width: 1680px;
}

.head {
  display: flex;
  align-items: flex-start;
  gap: 16px;
  padding: 16px 22px;
}
.head-actions {
  margin-left: auto;
  display: flex;
  gap: 10px;
  flex: 0 0 auto;
}

/* ---------------- 交付结论 ---------------- */
.verdict {
  display: flex;
  align-items: center;
  gap: 18px;
  margin-top: 16px;
  padding: 18px 24px;
  border-radius: 8px;
}
.verdict.ok {
  background: linear-gradient(96deg, #0f9b8e, #14b8a6);
  color: #fff;
}
.verdict.blocked {
  background: linear-gradient(96deg, #b03030, #cf3b3b);
  color: #fff;
}
.vd-icon {
  width: 46px;
  height: 46px;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.22);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 24px;
  font-weight: 700;
  flex: 0 0 auto;
}
.vd-body {
  flex: 1;
  min-width: 0;
}
.vd-title {
  font-size: 19px;
  font-weight: 700;
  margin-bottom: 4px;
}
.vd-text {
  font-size: 13px;
  opacity: 0.94;
  line-height: 1.7;
}
.vd-stat {
  display: flex;
  gap: 28px;
  flex: 0 0 auto;
}
.vds {
  text-align: center;
}
.vds-num {
  display: block;
  font-size: 22px;
  font-weight: 700;
}
.vds-lab {
  font-size: 11.5px;
  opacity: 0.88;
}

/* ---------------- 关卡 ---------------- */
.pad {
  padding: 16px 20px;
}
.gates {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(430px, 1fr));
  gap: 12px;
}
.gate {
  border: 1px solid var(--line);
  border-radius: 6px;
  padding: 12px 15px;
  background: #fff;
}
.gate.passed {
  background: #f7fdfc;
  border-color: #cfe6e2;
}
.gate.failed {
  background: #fffafa;
  border-color: #f0c8c8;
}
.g-head {
  display: flex;
  align-items: center;
  gap: 10px;
}
.g-icon {
  width: 24px;
  height: 24px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 13px;
  font-weight: 700;
  flex: 0 0 auto;
}
.gate.passed .g-icon {
  background: var(--teal);
  color: #fff;
}
.gate.failed .g-icon {
  background: var(--red);
  color: #fff;
}
.g-title {
  flex: 1;
  font-size: 13.5px;
  font-weight: 700;
  color: var(--ink);
}
.g-num {
  font-size: 11px;
  color: var(--grey);
  font-weight: 400;
  margin-right: 5px;
}
.g-detail {
  margin-top: 7px;
  font-size: 12px;
  color: var(--grey);
  line-height: 1.65;
}
.g-blockers {
  margin-top: 9px;
  padding-top: 9px;
  border-top: 1px dashed var(--line);
}
.g-blocker {
  font-size: 12px;
  color: var(--red);
  line-height: 1.7;
}
.g-suggest {
  margin-top: 7px;
  font-size: 12px;
  color: #7a5a17;
  background: var(--amber-soft);
  border-radius: 4px;
  padding: 7px 10px;
  line-height: 1.7;
}

/* ---------------- 成果表 ---------------- */
.d-name {
  font-weight: 600;
  color: var(--ink);
}
.req {
  margin-left: 6px;
  transform: scale(0.85);
}
.bl {
  line-height: 1.6;
}

/* ---------------- 说明 ---------------- */
.rules {
  margin-top: 16px;
  background: #f4f8fd;
  border: 1px solid #cfe0f5;
  border-radius: 6px;
  padding: 13px 18px;
  font-size: 12.5px;
  color: #23507f;
  line-height: 1.8;
}
.rules ol {
  margin: 7px 0 0;
  padding-left: 20px;
}
.rules li {
  margin-bottom: 4px;
}

.mf-foot {
  margin-top: 14px;
  font-size: 12px;
  color: var(--grey);
  text-align: right;
}
</style>
