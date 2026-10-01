<template>
  <StaffAccessGate route-id="visit_history" v-slot="{ can }">
    <VisitHistory v-if="can('list_visit_history')" />
    <p v-else role="status">{{ t('Нямате права за историята на посещенията.', 'You do not have access to visit history.') }}</p>
  </StaffAccessGate>
</template>
<script setup lang="ts">
import StaffAccessGate from './StaffAccessGate.vue'
import VisitHistory from './VisitHistory.vue'
import { useChildCenterLanguage } from './language'
const { t } = useChildCenterLanguage()
</script>
