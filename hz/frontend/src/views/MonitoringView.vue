<script setup lang="ts">
/**
 * 监测点台账页 —— 运维监测阶段的功能入口。
 */
import { computed } from 'vue'
import { useRoute } from 'vue-router'

import StageContextBar from '@/components/StageContextBar.vue'
import MonitoringLedger from '@/components/MonitoringLedger.vue'

const route = useRoute()
const projectId = computed(() => route.params.id as string)
const stage = computed(() => (route.query.stage as string) || null)
</script>

<template>
  <div class="page">
    <StageContextBar :project-id="projectId" :stage="stage" active="monitoring" />
    <MonitoringLedger :project-id="projectId" />
  </div>
</template>

<style scoped>
.page {
  max-width: 1680px;
}
</style>
