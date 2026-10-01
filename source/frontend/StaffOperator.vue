<template><StaffAccessGate route-id="operator_desk" v-slot="{ can }"><AccessPanel v-if="can('get_access_status')" /><OperatorDesk /><ScanOutcomes v-if="can('list_scan_outcomes')" /></StaffAccessGate></template>
<script setup lang="ts">
import StaffAccessGate from './StaffAccessGate.vue'
import OperatorDesk from './OperatorDesk.vue'
import AccessPanel from './AccessPanel.vue'
import ScanOutcomes from './ScanOutcomes.vue'
</script>
