<script setup lang="ts">
/**
 * 试桩台账页 —— 设计试桩 / 验收试桩阶段的功能入口。
 */
import { computed } from 'vue'
import { useRoute } from 'vue-router'

import StageContextBar from '@/components/StageContextBar.vue'
import TestPileLedger from '@/components/TestPileLedger.vue'

const route = useRoute()
const projectId = computed(() => route.params.id as string)
const stage = computed(() => (route.query.stage as string) || null)
</script>

<template>
  <div class="page">
    <StageContextBar :project-id="projectId" :stage="stage" active="test-piles" />
    <TestPileLedger :project-id="projectId" />
  </div>
</template>

<style scoped>
.page {
  max-width: 1680px;
}
</style>
