<script setup lang="ts">
import BacktestPage from './pages/BacktestPage.vue'
import FormulaScreenPage from './pages/FormulaScreenPage.vue'
import PortfolioBacktestPage from './pages/PortfolioBacktestPage.vue'
import StrategyFitnessPage from './pages/StrategyFitnessPage.vue'

const pathname = typeof window !== 'undefined' ? window.location.pathname : '/formula-screen'
const isStrategyFitness = pathname.startsWith('/strategy-fitness')
const isPortfolioBacktest = pathname.startsWith('/portfolio-backtest')
const isBacktest = pathname.startsWith('/backtest')
</script>

<template>
  <StrategyFitnessPage v-if="isStrategyFitness" />
  <PortfolioBacktestPage v-else-if="isPortfolioBacktest" />
  <BacktestPage v-else-if="isBacktest" />
  <FormulaScreenPage v-else />
</template>
