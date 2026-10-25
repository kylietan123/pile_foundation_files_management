<script setup lang="ts">
/**
 * AI 智能助手。
 *
 * **四条治理规则在这个界面上的体现**：
 *
 * 1. 回答带引用 —— 每条引用显示"文件 + 版本 + 页码/表号"，可点开看原文
 * 2. 检索先过权限 —— 页面明确说明"只检索你有权查看的内容"
 * 3. 会话限项目 —— 切换项目会新建会话，不跨项目续聊
 * 4. 四段式强制 —— 结论 / 依据 / 不确定性 / 责任声明 分块展示
 *
 * 另外两个刻意的设计：
 *   - 未配置模型时**明说"AI 未配置"**，只给检索原文，不编造答案
 *   - 提供"仅检索"模式，让用户直接看原文，不经过模型
 */
import { computed, onMounted, ref, nextTick } from 'vue'
import { ElMessage } from 'element-plus'
import { useRoute, useRouter } from 'vue-router'

import { aiApi, projectApi } from '@/api'
import { explainApiError } from '@/api/http'
import type { AIAnswer, AICitation, AIConversation, AIMessage, AIProviderStatus, ProjectInfo } from '@/api/types'
import { STAGE_LABEL, STAGE_ORDER } from '@/api/types'
import { formatDateTime } from '@/utils/format'

const route = useRoute()
const router = useRouter()

/** 当前项目（可在本项目内切换阶段范围） */
const projectId = ref<string>(route.params.id as string)
const projects = ref<ProjectInfo[]>([])
const provider = ref<AIProviderStatus | null>(null)

const conversations = ref<AIConversation[]>([])
const messages = ref<AIMessage[]>([])
const currentConvId = ref<string | null>(null)

const question = ref('')
const asking = ref(false)
const loading = ref(false)
const error = ref<string | null>(null)

/** 检索范围：限定阶段 */
const stageFilter = ref<string | null>(
  typeof route.query.stage === 'string' ? route.query.stage : null,
)
/** 是否把跨项目知识库纳入检索 */
const useKnowledgeBase = ref(true)

/** 仅检索模式（不调模型） */
const retrieveMode = ref(false)
const retrieveHits = ref<AICitation[]>([])

const scrollBox = ref<HTMLElement | null>(null)

const canUse = computed(() => !!projects.value.find((p) => p.id === projectId.value))

/** 快捷问题：把常用问法做成一键提问 */
const QUICK_QUESTIONS = [
  '本项目的设计输入参数有哪些？',
  '勘察报告里对桩端持力层有什么要求？',
  '地铁保护区桩型如何选择？',
  '当前设计变更会影响哪些内容？',
]

async function load() {
  loading.value = true
  error.value = null
  try {
    const [projs, st] = await Promise.all([
      projectApi.list(),
      aiApi.providerStatus(),
    ])
    projects.value = projs
    provider.value = st

    // 项目上下文的确定顺序（重要）：
    //   1. 路由参数 :id（从项目总览点进来）
    //   2. 查询参数 ?project=（外部链接/刷新时保留）
    //   3. 当前已选（若仍有效）
    //   4. 列表第一个
    // 之前只做了 3/4，导致从项目总览点「AI 助手」进来会落到第一个项目，
    // 看到的会话列表是空的 —— 而会话其实是按项目隔离的。
    const routeId = (route.params.id as string) || null
    const queryId = (route.query.project as string) || null
    const candidates = [routeId, queryId, projectId.value]
    for (const c of candidates) {
      if (c && projs.some((p) => p.id === c)) {
        projectId.value = c
        break
      }
    }
    if (!projs.some((p) => p.id === projectId.value) && projs.length) {
      projectId.value = projs[0].id
    }

    // 把当前项目写进地址栏，刷新后不丢上下文
    if (route.query.project !== projectId.value) {
      router.replace({ query: { ...route.query, project: projectId.value } })
    }

    await loadConversations()
  } catch (e) {
    error.value = explainApiError(e)
  } finally {
    loading.value = false
  }
}

async function loadConversations() {
  if (!canUse.value) return
  try {
    conversations.value = await aiApi.conversations(projectId.value)
  } catch {
    conversations.value = []
  }
}

onMounted(load)

async function openConversation(c: AIConversation) {
  currentConvId.value = c.id
  retrieveMode.value = false
  try {
    messages.value = await aiApi.messages(c.id)
    await scrollToBottom()
  } catch (e) {
    ElMessage.error(explainApiError(e))
  }
}

function newConversation() {
  currentConvId.value = null
  messages.value = []
  retrieveHits.value = []
  retrieveMode.value = false
}

async function switchProject(id: string) {
  projectId.value = id
  // 会话限项目：切项目必须新建会话，不能续聊
  newConversation()
  // 同步到地址栏，刷新后保持
  router.replace({ query: { ...route.query, project: id } })
  await loadConversations()
}

async function scrollToBottom() {
  await nextTick()
  const el = scrollBox.value
  if (el) el.scrollTop = el.scrollHeight
}

async function ask(q?: string) {
  const text = (q ?? question.value).trim()
  if (!text) {
    ElMessage.warning('请输入问题')
    return
  }
  if (!canUse.value) {
    ElMessage.warning('请先选择项目')
    return
  }

  if (retrieveMode.value) {
    await doRetrieve(text)
    return
  }

  asking.value = true
  // 先把用户提问推上去（乐观渲染）
  messages.value.push({
    id: `tmp-${Date.now()}`,
    role: 'user',
    content: text,
    has_citation: false,
    citations: [],
  })
  question.value = ''
  await scrollToBottom()

  try {
    const r = await aiApi.ask(projectId.value, {
      question: text,
      conversation_id: currentConvId.value,
      stage_code: stageFilter.value,
      include_knowledge_base: useKnowledgeBase.value,
    })
    const a: AIAnswer = r.data
    currentConvId.value = a.conversation_id

    // 用服务端返回的真实消息替换乐观渲染
    messages.value = await aiApi.messages(a.conversation_id)
    await loadConversations()

    if (a.degraded) {
      ElMessage.warning(a.degrade_reason || 'AI 未配置，仅返回检索原文')
    }
    await scrollToBottom()
  } catch (e) {
    ElMessage.error(explainApiError(e))
    // 失败时回滚乐观渲染
    messages.value = messages.value.filter((m) => !m.id.startsWith('tmp-'))
  } finally {
    asking.value = false
  }
}

async function doRetrieve(text: string) {
  asking.value = true
  try {
    retrieveHits.value = await aiApi.retrieve(
      projectId.value,
      text,
      stageFilter.value || undefined,
    )
    question.value = ''
    if (!retrieveHits.value.length) {
      ElMessage.info('没有检索到相关内容')
    }
  } catch (e) {
    ElMessage.error(explainApiError(e))
  } finally {
    asking.value = false
  }
}

async function giveFeedback(m: AIMessage, fb: 'USEFUL' | 'USELESS') {
  try {
    await aiApi.feedback(m.id, fb)
    m.feedback = fb
    ElMessage.success(fb === 'USEFUL' ? '已标记为有用' : '已标记为无用，我们会改进检索')
  } catch (e) {
    ElMessage.error(explainApiError(e))
  }
}

/** 引用抽屉 */
const citeDrawer = ref(false)
const activeCite = ref<AICitation | null>(null)

function showCite(c: AICitation) {
  activeCite.value = c
  citeDrawer.value = true
}

function openSourceDoc(c: AICitation) {
  // 有源版本就直接去文件与版本页核对原文
  router.push({ name: 'documents', params: { id: projectId.value } })
  void c
}

const stageName = (s?: string | null) =>
  s ? STAGE_LABEL[s as keyof typeof STAGE_LABEL] || s : ''
</script>

<template>
  <div class="page">
    <!-- 顶部 -->
    <div class="head app-card">
      <div class="head-l">
        <div class="sec-title" style="margin-bottom: 10px">
          AI 智能助手
          <span class="more" @click="newConversation">新会话</span>
        </div>
        <p class="t-grey t-sm" style="margin: 0">
          <b class="t-amber">回答必须带引用</b>，没有引用的回答不展示。
          检索只覆盖<b>你有权查看的已发布版本</b> —— 权限过滤在检索之前完成。
        </p>
      </div>
      <div class="head-actions">
        <el-select
          :model-value="projectId"
          size="small"
          style="width: 190px"
          @change="switchProject"
        >
          <el-option v-for="p in projects" :key="p.id" :label="p.short_name || p.name" :value="p.id" />
        </el-select>
        <el-select v-model="stageFilter" size="small" placeholder="全部阶段" clearable style="width: 130px">
          <el-option v-for="s in STAGE_ORDER" :key="s" :label="STAGE_LABEL[s]" :value="s" />
        </el-select>
        <el-switch v-model="retrieveMode" size="small" active-text="仅检索" />
      </div>
    </div>

    <!-- 提供方状态：未配置时明确告知，不假装可用 -->
    <el-alert
      v-if="provider && !provider.available"
      type="warning"
      show-icon
      :closable="false"
      style="margin-top: 14px"
      title="AI 模型未配置"
    >
      <div style="font-size: 12.5px; line-height: 1.8">
        {{ provider.note }}
        <br />
        <b>这不是功能缺失</b>，而是刻意设计：院内如何部署（自建 / 调云端）还没定，
        所以把部署方式做成了配置项。配置后即可获得归纳性回答，<b>接口与界面都不需要改</b>。
        <br />
        配置方法（<code>.env</code>）：
        <code>LLM_PROVIDER=local</code> 或 <code>cloud</code>，
        再配 <code>LLM_BASE_URL</code> 与 <code>LLM_MODEL</code>。
      </div>
    </el-alert>

    <el-alert
      v-else-if="provider"
      type="success"
      show-icon
      :closable="false"
      style="margin-top: 14px"
      :title="`AI 已就绪（${provider.mode}${provider.model ? ' · ' + provider.model : ''}）`"
    />

    <el-skeleton v-if="loading" :rows="8" animated style="margin-top: 16px" />
    <el-alert v-else-if="error" :title="error" type="error" show-icon :closable="false" />

    <div v-else class="layout">
      <!-- 左：会话列表 -->
      <div class="side app-card">
        <div class="side-h">
          会话（{{ conversations.length }}）
          <el-button link type="primary" size="small" @click="newConversation">＋</el-button>
        </div>
        <div v-if="!conversations.length" class="empty t-grey">还没有会话</div>
        <div
          v-for="c in conversations"
          :key="c.id"
          class="conv"
          :class="{ active: currentConvId === c.id }"
          @click="openConversation(c)"
        >
          <div class="conv-t">{{ c.title || '未命名会话' }}</div>
          <div class="t-grey t-sm">
            {{ c.message_count }} 条消息
            <span v-if="c.updated_at"> · {{ formatDateTime(c.updated_at) }}</span>
          </div>
        </div>
        <div class="side-note t-grey t-sm">
          会话绑定当前项目。
          切换项目会新建会话 —— 内部试用期<b>不允许跨项目检索</b>，
          避免把别的项目的数据带进来。
        </div>
      </div>

      <!-- 中：对话 -->
      <div class="chat app-card">
        <div ref="scrollBox" class="chat-body">
          <!-- 空态与快捷问题 -->
          <div v-if="!messages.length && !retrieveHits.length" class="welcome">
            <div class="wc-title">可以这样问我</div>
            <div class="wc-tip t-grey t-sm">
              我会检索本项目的已发布文件（勘察报告、设计说明、计算书等）
              与跨项目知识库里已闭环的经验，然后<b>带引用</b>回答。
            </div>
            <div class="quick">
              <div v-for="q in QUICK_QUESTIONS" :key="q" class="q" @click="ask(q)">{{ q }}</div>
            </div>
          </div>

          <!-- 对话消息 -->
          <div v-for="m in messages" :key="m.id" class="msg" :class="m.role">
            <div class="avatar">{{ m.role === 'user' ? '我' : 'AI' }}</div>
            <div class="bubble">
              <template v-if="m.role === 'user'">
                <div class="u-text">{{ m.content }}</div>
              </template>

              <template v-else>
                <!-- 无引用 → 不展示（治理规则） -->
                <div v-if="!m.has_citation" class="no-cite">
                  <b>该回答没有引用来源，已按规则不予展示。</b>
                  <div class="t-sm" style="margin-top: 4px">
                    没有引用的 AI 回答不允许给用户看 —— 这是防幻觉的机制。
                    请换个问法，或到「文件与版本」确认相关内容是否已发布。
                  </div>
                </div>

                <template v-else>
                  <div v-if="m.conclusion" class="sec">
                    <div class="sec-h">结论</div>
                    <div class="sec-b">{{ m.conclusion }}</div>
                  </div>

                  <div v-if="m.citations.length" class="sec">
                    <div class="sec-h">依据</div>
                    <div class="cites">
                      <div
                        v-for="(c, i) in m.citations"
                        :key="c.id || i"
                        class="cite"
                        :class="{ kb: c.source_type === 'KNOWLEDGE_BASE' }"
                        @click="showCite(c)"
                      >
                        <span class="cite-n">{{ i + 1 }}</span>
                        <span class="cite-t">
                          {{ c.locator || '未知来源' }}
                        </span>
                        <el-tag
                          v-if="c.source_type === 'KNOWLEDGE_BASE'"
                          size="small"
                          type="success"
                          effect="plain"
                        >
                          知识库
                        </el-tag>
                      </div>
                    </div>
                  </div>

                  <div v-if="m.uncertainty" class="sec">
                    <div class="sec-h warn">不确定性</div>
                    <div class="sec-b warn-b">{{ m.uncertainty }}</div>
                  </div>

                  <div class="disclaim">{{ m.disclaimer }}</div>

                  <div class="fb">
                    <span class="t-grey t-sm">这个回答有用吗？</span>
                    <el-button
                      link
                      size="small"
                      :type="m.feedback === 'USEFUL' ? 'success' : 'default'"
                      @click="giveFeedback(m, 'USEFUL')"
                    >
                      👍 有用
                    </el-button>
                    <el-button
                      link
                      size="small"
                      :type="m.feedback === 'USELESS' ? 'danger' : 'default'"
                      @click="giveFeedback(m, 'USELESS')"
                    >
                      👎 无用
                    </el-button>
                    <span v-if="m.latency_ms" class="t-grey t-sm ml8">{{ m.latency_ms }} ms</span>
                    <span v-if="m.model" class="t-grey t-sm ml8">{{ m.model }}</span>
                  </div>
                </template>
              </template>
            </div>
          </div>

          <!-- 仅检索结果 -->
          <div v-if="retrieveMode && retrieveHits.length" class="retrieve">
            <div class="rt-title">检索结果（{{ retrieveHits.length }}）· 来自已发布版本</div>
            <div v-for="(c, i) in retrieveHits" :key="i" class="rt-item" @click="showCite(c)">
              <div class="rt-head">
                <span class="cite-n">{{ i + 1 }}</span>
                <b>{{ c.locator || '未知来源' }}</b>
                <el-tag
                  v-if="c.source_type === 'KNOWLEDGE_BASE'"
                  size="small"
                  type="success"
                  effect="plain"
                >
                  知识库
                </el-tag>
                <span v-if="c.score != null" class="t-grey t-sm" style="margin-left: auto">
                  相关性 {{ c.score.toFixed(2) }}
                </span>
              </div>
              <div class="rt-text">{{ c.quoted_text }}</div>
            </div>
          </div>

          <div v-if="asking" class="thinking t-grey">正在检索并组织回答…</div>
        </div>

        <div class="chat-foot">
          <el-input
            v-model="question"
            type="textarea"
            :rows="2"
            :placeholder="retrieveMode ? '输入关键词，只看原文不生成回答…' : '问点什么…（Enter 发送，Shift+Enter 换行）'"
            resize="none"
            @keydown.enter.exact.prevent="ask()"
          />
          <div class="foot-bar">
            <el-checkbox v-if="!retrieveMode" v-model="useKnowledgeBase" size="small">
              纳入跨项目知识库
            </el-checkbox>
            <span class="t-grey t-sm">
              检索范围：{{ stageFilter ? stageName(stageFilter) : '全部阶段' }} · 仅已发布版本
            </span>
            <el-button
              type="primary"
              size="small"
              :loading="asking"
              style="margin-left: auto"
              @click="ask()"
            >
              {{ retrieveMode ? '检索' : '发送' }}
            </el-button>
          </div>
        </div>
      </div>
    </div>

    <!-- ============ 引用详情 ============ -->
    <el-drawer v-model="citeDrawer" title="引用来源" size="620px">
      <template v-if="activeCite">
        <el-descriptions :column="1" border size="small">
          <el-descriptions-item label="来源">
            <span v-if="activeCite.source_type === 'KNOWLEDGE_BASE'">
              跨项目知识库（已闭环问题经验）
            </span>
            <span v-else>项目文件</span>
          </el-descriptions-item>
          <el-descriptions-item label="定位">
            <b>{{ activeCite.locator || '—' }}</b>
          </el-descriptions-item>
          <el-descriptions-item v-if="activeCite.document_title" label="文件">
            {{ activeCite.document_title }}
          </el-descriptions-item>
          <el-descriptions-item v-if="activeCite.version_no" label="版本">
            <b class="t-teal">{{ activeCite.version_no }}</b>
          </el-descriptions-item>
          <el-descriptions-item v-if="activeCite.section_path" label="章节">
            {{ activeCite.section_path }}
          </el-descriptions-item>
          <el-descriptions-item v-if="activeCite.page_no" label="页码">
            P.{{ activeCite.page_no }}
          </el-descriptions-item>
          <el-descriptions-item v-if="activeCite.score != null" label="相关性">
            {{ activeCite.score.toFixed(3) }}
          </el-descriptions-item>
        </el-descriptions>

        <div class="sec-title" style="margin-top: 18px">原文片段</div>
        <pre class="quote">{{ activeCite.quoted_text || '（无原文）' }}</pre>

        <div v-if="activeCite.source_type !== 'KNOWLEDGE_BASE'" class="drawer-foot">
          <el-button size="small" @click="openSourceDoc(activeCite)">
            到「文件与版本」核对原文
          </el-button>
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
  align-items: center;
  gap: 10px;
  flex: 0 0 auto;
}

.layout {
  display: grid;
  grid-template-columns: 280px 1fr;
  gap: 16px;
  margin-top: 16px;
  align-items: start;
  height: calc(100vh - 300px);
  min-height: 480px;
}

/* ---------------- 左侧会话 ---------------- */
.side {
  padding: 0;
  overflow: hidden;
  max-height: 100%;
  display: flex;
  flex-direction: column;
}
.side-h {
  padding: 11px 16px;
  border-bottom: 1px solid var(--line);
  font-weight: 700;
  font-size: 13.5px;
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.empty {
  padding: 24px 16px;
  text-align: center;
  font-size: 13px;
}
.conv {
  padding: 10px 16px;
  border-bottom: 1px solid #f0f3f8;
  cursor: pointer;
  border-left: 3px solid transparent;
}
.conv:hover {
  background: #f7f9fc;
}
.conv.active {
  background: var(--blue-soft);
  border-left-color: var(--blue);
}
.conv-t {
  font-size: 13px;
  font-weight: 600;
  color: var(--ink);
  margin-bottom: 2px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.side-note {
  margin-top: auto;
  padding: 11px 16px;
  border-top: 1px dashed var(--line);
  line-height: 1.7;
  font-size: 11.5px;
}

/* ---------------- 对话区 ---------------- */
.chat {
  display: flex;
  flex-direction: column;
  max-height: 100%;
  overflow: hidden;
}
.chat-body {
  flex: 1;
  overflow-y: auto;
  padding: 18px 22px;
}

.welcome {
  padding: 20px 0;
}
.wc-title {
  font-size: 15px;
  font-weight: 700;
  color: var(--ink);
  margin-bottom: 6px;
}
.wc-tip {
  line-height: 1.75;
  margin-bottom: 16px;
}
.quick {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.q {
  border: 1px solid var(--line);
  border-radius: 6px;
  padding: 10px 14px;
  font-size: 13px;
  color: var(--ink-2);
  cursor: pointer;
  transition: all 0.15s;
  background: #fbfcfe;
}
.q:hover {
  border-color: var(--blue);
  background: var(--blue-soft);
  color: var(--blue);
}

/* ---------------- 消息 ---------------- */
.msg {
  display: flex;
  gap: 10px;
  margin-bottom: 18px;
}
.msg.user {
  flex-direction: row-reverse;
}
.avatar {
  width: 30px;
  height: 30px;
  border-radius: 50%;
  background: linear-gradient(135deg, #1e6fd9, #0f9b8e);
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  font-weight: 700;
  flex: 0 0 auto;
}
.msg.user .avatar {
  background: #6b7a8d;
}
.bubble {
  max-width: 78%;
  min-width: 0;
}
.msg.user .bubble {
  display: flex;
  justify-content: flex-end;
}
.u-text {
  background: var(--blue);
  color: #fff;
  padding: 10px 14px;
  border-radius: 10px 10px 2px 10px;
  font-size: 13.5px;
  line-height: 1.7;
}
.msg.assistant .bubble {
  background: #fff;
  border: 1px solid var(--line);
  border-radius: 10px 10px 10px 2px;
  padding: 14px 16px;
}

.no-cite {
  background: var(--red-soft);
  border: 1px solid #f0c8c8;
  color: #8a2f2f;
  border-radius: 5px;
  padding: 11px 14px;
  font-size: 12.5px;
  line-height: 1.75;
}

.sec {
  margin-bottom: 12px;
}
.sec-h {
  font-size: 11.5px;
  font-weight: 700;
  color: var(--blue);
  letter-spacing: 0.5px;
  margin-bottom: 5px;
}
.sec-h.warn {
  color: var(--amber);
}
.sec-b {
  font-size: 13.5px;
  color: var(--ink);
  line-height: 1.8;
  white-space: pre-wrap;
}
.warn-b {
  background: var(--amber-soft);
  border-radius: 4px;
  padding: 8px 11px;
  font-size: 12.5px;
  color: #7a5a17;
}

.cites {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.cite {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  border: 1px solid #bcd6f5;
  background: var(--blue-soft);
  color: var(--blue);
  border-radius: 4px;
  padding: 4px 9px;
  font-size: 12px;
  cursor: pointer;
  transition: all 0.15s;
  max-width: 100%;
}
.cite:hover {
  background: #d6e7fb;
}
.cite.kb {
  border-color: #b8e0db;
  background: var(--teal-soft);
  color: #0b6b62;
}
.cite-n {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 15px;
  height: 15px;
  border-radius: 3px;
  background: currentColor;
  color: #fff;
  font-size: 10px;
  font-weight: 700;
  flex: 0 0 auto;
}
.cite-t {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.disclaim {
  font-size: 11.5px;
  color: var(--amber);
  background: #fffaf0;
  border: 1px solid #f0dcb0;
  border-radius: 4px;
  padding: 7px 10px;
  line-height: 1.7;
}

.fb {
  margin-top: 11px;
  padding-top: 10px;
  border-top: 1px dashed var(--line);
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.ml8 {
  margin-left: 8px;
}

/* ---------------- 仅检索 ---------------- */
.retrieve {
  border-top: 1px dashed var(--line);
  padding-top: 14px;
}
.rt-title {
  font-size: 13px;
  font-weight: 700;
  margin-bottom: 10px;
}
.rt-item {
  border: 1px solid var(--line);
  border-radius: 6px;
  padding: 10px 13px;
  margin-bottom: 9px;
  cursor: pointer;
  background: #fbfcfe;
}
.rt-item:hover {
  border-color: var(--blue);
}
.rt-head {
  display: flex;
  align-items: center;
  gap: 7px;
  font-size: 12.5px;
}
.rt-text {
  margin-top: 6px;
  font-size: 12.5px;
  color: var(--ink-2);
  line-height: 1.75;
  white-space: pre-wrap;
}

.thinking {
  font-size: 13px;
  padding: 8px 0;
}

/* ---------------- 输入区 ---------------- */
.chat-foot {
  border-top: 1px solid var(--line);
  padding: 12px 16px;
  background: #fbfcfe;
}
.foot-bar {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-top: 8px;
}

/* ---------------- 抽屉 ---------------- */
.quote {
  font-family: 'Microsoft YaHei', monospace;
  font-size: 12.5px;
  line-height: 1.9;
  color: var(--ink-2);
  background: #f7f9fc;
  border-radius: 5px;
  padding: 13px 16px;
  margin: 0;
  white-space: pre-wrap;
  word-break: break-word;
}
.drawer-foot {
  margin-top: 16px;
}

@media (max-width: 1200px) {
  .layout {
    grid-template-columns: 1fr;
    height: auto;
  }
}
</style>
