<script setup lang="ts">
import Desk from './Desk.vue'
defineProps<{ locale?: string }>()
</script>
<template><Desk initial-section="visits" :locale="locale" /></template>
