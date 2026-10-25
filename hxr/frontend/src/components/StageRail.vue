<script setup lang="ts">
/**
 * 7 阶段迷你进度条（项目卡片用）。
 *
 * 阶段是**同一个项目的 7 个环节**，不是 7 个独立系统 —— 这个组件是这句话的视觉表达。
 */
import { computed } from 'vue'

import { STAGE_LABEL, STAGE_ORDER, type StageCode, type StageStatus } from '@/api/types'

const props = defineProps<{
  /** 当前阶段 */
  current: StageCode
  /** 各阶段状态，缺省按"当前阶段之前为已完成"推断 */
  statuses?: Record<string, StageStatus>
}>()

const currentIndex = computed(() => STAGE_ORDER.indexOf(props.current))

function stateOf(code: StageCode, i: number): 'done' | 'current' | 'todo' {
  if (props.statuses?.[code] === 'COMPLETED') return 'done'
  if (props.statuses?.[code] === 'IN_PROGRESS') return 'current'
  if (i < currentIndex.value) return 'done'
  if (i === currentIndex.value) return 'current'
  return 'todo'
}
</script>

<template>
  <div class="stage-rail-mini">
    <template v-for="(code, i) in STAGE_ORDER" :key="code">
      <div
        class="node"
        :class="{
          done: stateOf(code, i) === 'done',
          current: stateOf(code, i) === 'current',
        }"
      >
        <div class="dot" />
        {{ STAGE_LABEL[code] }}
      </div>
      <div
        v-if="i < STAGE_ORDER.length - 1"
        class="link"
        :class="{ done: stateOf(code, i) === 'done' }"
      />
    </template>
  </div>
</template>
