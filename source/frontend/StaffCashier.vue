<template>
  <StaffAccessGate route-id="cashier_desk" v-slot="{ can }">
    <main v-if="can('list_checkout_accounts') && can('get_checkout_account')" class="cashier-page">
      <header><h1>{{ t('Каса', 'Checkout') }}</h1><button @click="toggleLanguage" :aria-label="t('Смени езика', 'Change language')">{{ language === 'bg' ? 'EN' : 'BG' }}</button></header>
      <p>{{ t('Операторът приключва играта. Тук проверявате и плащате сметката.', 'The operator finishes playing. Review and settle the account here.') }}</p>
      <AccountDesk cashier initial-filter="closed" />
    </main>
    <p v-else role="status">{{ t('Нямате права за преглед на сметките.', 'You do not have access to accounts.') }}</p>
  </StaffAccessGate>
</template>
<script setup lang="ts">
import StaffAccessGate from './StaffAccessGate.vue'
import AccountDesk from './AccountDesk.vue'
import { useChildCenterLanguage } from './language'
const { t, language, toggleLanguage } = useChildCenterLanguage()
</script>
<style scoped>
.cashier-page { max-width: 90rem; margin: 0 auto; padding: clamp(1rem, 3vw, 2.5rem); color: var(--text-primary); }
header { display: flex; justify-content: space-between; align-items: center; gap: 1rem; }
h1 { margin: 0; } p { color: var(--text-secondary); }
button { font: inherit; padding: .6rem; border: 1px solid var(--card-border); border-radius: .5rem; color: inherit; background: var(--card-bg); cursor: pointer; }
</style>
