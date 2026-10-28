<script setup lang="ts">
/**
 * 跨项目知识库。
 *
 * 一个项目踩过的坑，别的项目不用再踩 —— 这是产品越用越有价值的地方。
 *
 * 数据来源：所有项目里**已闭环并沉淀**的问题经验。
 * 这也是 **AI 检索层的数据来源**：接入向量库后换成语义检索，接口形态不变。
 */
import { computed, onMounted, ref } from 'vue'

import { knowledgeApi } from '@/api'
import { explainApiError } from '@/api/http'
import type { KnowledgeItem } from '@/api/types'
import { SEVERITY_LABEL, SEVERITY_TAG, Severity } from '@/api/types'
import { formatDate } from '@/utils/format'

const loading = ref(false)
const error = ref<string | null>(null)
const items = ref<KnowledgeItem[]>([])
const keyword = ref('')
const activeStage = ref<string | null>(null)

/** 阶段筛选选项（从数据里推导，避免硬编码不存在的阶段） */
const stageOptions = computed(() => {
  const m = new Map<string, string>()
  for (const i of items.value) {
    if (i.stage_code) m.set(i.stage_code, i.stage_label || i.stage_code)
  }
  return [...m.entries()].map(([code, label]) => ({ code, label }))
})

const filtered = computed(() =>
  activeStage.value
    ? items.value.filter((i) => i.stage_code === activeStage.value)
    : items.value,
)

async function load() {
  loading.value = true
  error.value = null
  try {
    items.value = await knowledgeApi.search({ keyword: keyword.value || undefined, limit: 200 })
  } catch (e) {
    error.value = explainApiError(e)
    items.value = []
  } finally {
    loading.value = false
  }
}

onMounted(load)

const sevTag = (s: string) => SEVERITY_TAG[s as Severity] ?? 'info'

/** 摘要按行渲染，保留【问题】【分析】这类结构化前缀 */
function linesOf(text?: string | null): { label: string; body: string }[] {
  if (!text) return []
  const out: { label: string; body: string }[] = []
  for (const raw of text.split('\n')) {
    const m = raw.match(/^【(.+?)】(.*)$/)
    if (m) out.push({ label: m[1], body: m[2].trim() })
    else if (raw.trim()) out.push({ label: '', body: raw.trim() })
  }
  return out
}
</script>

<template>
  <div class="page">
    <!-- 顶部 -->
    <div class="head app-card">
      <div>
        <div class="sec-title" style="margin-bottom: 10px">
          跨项目知识库
          <span class="more" style="cursor: default">{{ items.length }} 条已沉淀经验</span>
        </div>
        <p class="t-grey t-sm" style="margin: 0">
          汇总所有项目里<b>已闭环并沉淀</b>的问题经验 ——
          一个项目踩过的坑，别的项目不用再踩。
          <span class="t-blue">这也是 AI 检索层的数据来源。</span>
        </p>
      </div>
      <div class="head-actions">
        <el-input
          v-model="keyword"
          placeholder="搜索问题、分析结论、处理办法…"
          clearable
          style="width: 300px"
          @keyup.enter="load"
          @clear="load"
        >
          <template #append>
            <el-button @click="load">搜索</el-button>
          </template>
        </el-input>
      </div>
    </div>

    <!-- 阶段筛选 -->
    <div v-if="stageOptions.length" class="filters">
      <span class="t-grey t-sm">阶段：</span>
      <el-tag
        :type="activeStage === null ? 'primary' : 'info'"
        :effect="activeStage === null ? 'dark' : 'plain'"
        size="small"
        style="cursor: pointer"
        @click="activeStage = null"
      >
        全部
      </el-tag>
      <el-tag
        v-for="s in stageOptions"
        :key="s.code"
        :type="activeStage === s.code ? 'primary' : 'info'"
        :effect="activeStage === s.code ? 'dark' : 'plain'"
        size="small"
        style="cursor: pointer"
        @click="activeStage = s.code"
      >
        {{ s.label }}
      </el-tag>
    </div>

    <el-skeleton v-if="loading" :rows="6" animated style="margin-top: 16px" />
    <el-alert v-else-if="error" :title="error" type="error" show-icon :closable="false" />

    <div v-else-if="!filtered.length" class="app-card empty">
      <div class="em-title">还没有沉淀的知识条目</div>
      <div class="t-grey t-sm">
        到项目的「问题管理」里，把已闭环的问题点「沉淀为知识」即可。
        <br />
        只有<b>已闭环</b>的问题才能沉淀 —— 未经验证的处理办法不该进知识库，
        否则会把错误经验传播到后续项目。
      </div>
    </div>

    <div v-else class="grid">
      <div v-for="k in filtered" :key="k.issue_id" class="kcard app-card">
        <div class="kc-head">
          <div class="kc-title">{{ k.title }}</div>
          <el-tag v-if="k.severity" :type="sevTag(k.severity)" size="small" effect="light">
            {{ SEVERITY_LABEL[k.severity] }}
          </el-tag>
        </div>
        <div class="kc-meta t-grey t-sm">
          <span v-if="k.project_name">{{ k.project_name }}</span>
          <span v-if="k.stage_label"> · {{ k.stage_label }}</span>
          <span v-if="k.closed_at"> · 闭环于 {{ formatDate(k.closed_at) }}</span>
          <span v-if="k.issue_no" class="t-mono"> · {{ k.issue_no }}</span>
        </div>

        <div class="kc-body">
          <div v-for="(l, i) in linesOf(k.knowledge_summary)" :key="i" class="kc-line">
            <span v-if="l.label" class="kc-label">{{ l.label }}</span>
            <span class="kc-text">{{ l.body }}</span>
          </div>
        </div>
      </div>
    </div>
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
  flex: 0 0 auto;
}

.filters {
  display: flex;
  align-items: center;
  gap: 7px;
  flex-wrap: wrap;
  margin-top: 14px;
  padding: 10px 16px;
  background: #fff;
  border: 1px solid var(--line);
  border-radius: 6px;
}

.empty {
  margin-top: 16px;
  padding: 50px 20px;
  text-align: center;
}
.em-title {
  font-size: 15px;
  font-weight: 700;
  margin-bottom: 8px;
  color: var(--ink);
}

.grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(520px, 1fr));
  gap: 16px;
  margin-top: 16px;
}

.kcard {
  padding: 15px 18px;
  display: flex;
  flex-direction: column;
}
.kc-head {
  display: flex;
  align-items: flex-start;
  gap: 10px;
}
.kc-title {
  font-size: 14.5px;
  font-weight: 700;
  color: var(--ink);
  line-height: 1.5;
  flex: 1;
}
.kc-meta {
  margin: 5px 0 11px;
  font-size: 12px;
}

.kc-body {
  flex: 1;
  background: #f7f9fc;
  border-radius: 5px;
  padding: 11px 13px;
}
.kc-line {
  display: flex;
  gap: 8px;
  font-size: 12.5px;
  line-height: 1.8;
  color: var(--ink-2);
  margin-bottom: 5px;
}
.kc-line:last-child {
  margin-bottom: 0;
}
.kc-label {
  flex: 0 0 auto;
  font-weight: 700;
  color: var(--blue);
}
.kc-text {
  flex: 1;
}
</style>
