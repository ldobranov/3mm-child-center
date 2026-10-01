<template><StaffAccessGate route-id="active_visits" v-slot="{ can }"><AccessPanel v-if="can('get_access_status')" /><ActiveVisits v-if="can('list_active_visits')" /><p v-else role="status">{{ t('Нямате права за посещения.', 'You do not have access to visits.') }}</p><ScanOutcomes v-if="can('list_scan_outcomes')" /></StaffAccessGate></template>
<script setup lang="ts">
import StaffAccessGate from './StaffAccessGate.vue'
import ActiveVisits from './ActiveVisits.vue'
import AccessPanel from './AccessPanel.vue'
import ScanOutcomes from './ScanOutcomes.vue'
import { useChildCenterLanguage } from './language'
const { t } = useChildCenterLanguage()
</script>
