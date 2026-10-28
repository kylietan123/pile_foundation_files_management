<script setup lang="ts">
/**
 * 证照台账页 —— 前期调研阶段的功能入口。
 */
import { computed } from 'vue'
import { useRoute } from 'vue-router'

import StageContextBar from '@/components/StageContextBar.vue'
import LicenseLedger from '@/components/LicenseLedger.vue'

const route = useRoute()
const projectId = computed(() => route.params.id as string)
const stage = computed(() => (route.query.stage as string) || null)
</script>

<template>
  <div class="page">
    <StageContextBar :project-id="projectId" :stage="stage" active="licenses" />
    <LicenseLedger :project-id="projectId" />
  </div>
</template>

<style scoped>
.page {
  max-width: 1680px;
}
</style>
