<script setup lang="ts">
import BacktestPage from './pages/BacktestPage.vue'
import FormulaScreenPage from './pages/FormulaScreenPage.vue'

const isBacktest = typeof window !== 'undefined' && window.location.pathname.startsWith('/backtest')
</script>

<template>
  <BacktestPage v-if="isBacktest" />
  <FormulaScreenPage v-else />
</template>
