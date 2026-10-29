<script setup lang="ts">
import Commerce from './Commerce.vue'
defineProps<{locale?:string}>()
</script>
<template><Commerce :locale="locale" cashier/></template>
