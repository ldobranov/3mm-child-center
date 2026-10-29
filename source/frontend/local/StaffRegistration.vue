<script setup lang="ts">
import Registration from './Registration.vue'
defineProps<{locale?:string}>()
</script>
<template><Registration :locale="locale" /></template>
