<script setup lang="ts">
/**
 * 阶段上下文栏：进入某个阶段后的「阶段切换 + 功能切换」导航。
 *
 * 这是「阶段优先」导航的核心：点进某个阶段后，顶部始终有这一条，
 * 用户随时能换阶段、或在本阶段内切换 文件/变更/问题/成果/台账。
 * 全阶段（stage 为空）时表示项目整体视图，各功能不按阶段过滤。
 */
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { STAGE_LABEL, STAGE_ORDER } from '@/api/types'

const props = defineProps<{
  projectId: string
  /** 当前阶段码；为空表示「全阶段」视图 */
  stage?: string | null
  /** 当前所在功能，用于高亮与阶段切换后停留 */
  active: string
}>()

const router = useRouter()

const features: { name: string; label: string; stages?: string[] }[] = [
  { name: 'documents', label: '文件与版本' },
  // 设计输入 / 设计变更 / 设计成果：只在「设计」阶段显示
  // 设计输入是设计阶段的上游资料入口，和文件、变更、成果并列，
  // 不再作为项目总览上的一个全局按钮（那样每个账号看到都不一样）。
  { name: 'design-inputs', label: '设计输入管理', stages: ['DESIGN'] },
  // 桩基选型：设计阶段的方案决策模块（规则引擎给建议、设计人确认）
  { name: 'pile-selection', label: '桩基选型', stages: ['DESIGN'] },
  { name: 'changes', label: '设计变更', stages: ['DESIGN'] },
  { name: 'issues', label: '问题管理' },
  { name: 'deliverables', label: '设计成果', stages: ['DESIGN'] },
  { name: 'ledger', label: '文件台账' },
  // 试桩台账：只在试桩相关阶段显示
  { name: 'test-piles', label: '试桩台账', stages: ['DESIGN_TEST_PILE', 'ACCEPT_TEST_PILE'] },
  // 钻孔台账：只在地质勘察阶段显示
  { name: 'boreholes', label: '钻孔台账', stages: ['INVESTIGATION'] },
  // 证照台账：只在前期调研阶段显示
  { name: 'licenses', label: '证照台账', stages: ['PRE_SURVEY'] },
  // 监测点台账：只在运维监测阶段显示
  { name: 'monitoring', label: '监测点台账', stages: ['MONITORING'] },
]

const visibleFeatures = computed(() =>
  features.filter((f) => !f.stages || (props.stage ? f.stages.includes(props.stage) : false)),
)

function goFeature(name: string) {
  router.push({
    name,
    params: { id: props.projectId },
    query: props.stage ? { stage: props.stage } : {},
  })
}

function goStage(code: string | null) {
  // 切换阶段后，若当前功能在该阶段不可用（如试桩台账切到设计阶段），回落到「文件与版本」
  const cur = features.find((f) => f.name === props.active)
  const keep = !code || !cur?.stages || cur.stages.includes(code)
  router.push({
    name: keep ? props.active || 'documents' : 'documents',
    params: { id: props.projectId },
    query: code ? { stage: code } : {},
  })
}

function onStageChange(v: string) {
  goStage(v || null)
}
</script>

<template>
  <div class="stage-context">
    <div class="sc-stage">
      <span class="sc-label">阶段</span>
      <el-select
        :model-value="stage || ''"
        size="small"
        class="sc-select"
        @change="onStageChange"
      >
        <el-option label="全阶段" value="" />
        <el-option v-for="c in STAGE_ORDER" :key="c" :label="STAGE_LABEL[c]" :value="c" />
      </el-select>
    </div>
    <nav class="sc-tabs">
      <span
        v-for="f in visibleFeatures"
        :key="f.name"
        class="sc-tab"
        :class="{ on: active === f.name }"
        @click="goFeature(f.name)"
      >
        {{ f.label }}
      </span>
    </nav>
  </div>
</template>

<style scoped>
.stage-context {
  display: flex;
  align-items: center;
  gap: 16px;
  background: #fff;
  border: 1px solid var(--line, #e3e8f0);
  border-radius: 6px;
  padding: 8px 14px;
  margin-bottom: 14px;
  flex-wrap: wrap;
}
.sc-stage {
  display: flex;
  align-items: center;
  gap: 8px;
}
.sc-label {
  font-size: 12px;
  color: #8793a5;
}
.sc-select {
  width: 150px;
}
.sc-tabs {
  display: flex;
  gap: 4px;
  flex-wrap: wrap;
}
.sc-tab {
  font-size: 13px;
  color: #4a5866;
  cursor: pointer;
  padding: 5px 12px;
  border-radius: 4px;
  transition: background 0.15s, color 0.15s;
  user-select: none;
}
.sc-tab:hover {
  background: #eef3fa;
}
.sc-tab.on {
  background: var(--blue, #1a6bb0);
  color: #fff;
  font-weight: 600;
}
</style>
