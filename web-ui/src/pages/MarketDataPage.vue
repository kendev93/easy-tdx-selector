<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'

import { FormulaScreenApiError } from '../api/formulaScreen'
import { fetchLocalChart, fetchLocalInstruments } from '../api/marketData'
import type {
  LocalInstrument,
  LocalInstrumentMeta,
  LocalMarketChart,
  LocalMarketScope,
  MarketChartPeriod,
} from '../types'
import MarketCandlestickChart from '../components/MarketCandlestickChart.vue'

const MA_OPTIONS = [
  { key: 'ma5', label: 'MA5' },
  { key: 'ma10', label: 'MA10' },
  { key: 'ma20', label: 'MA20' },
  { key: 'ma60', label: 'MA60' },
]

const form = reactive({
  vipdocPath: '/data/vipdoc',
  market: 'all' as LocalMarketScope,
  keyword: '',
  page: 1,
  pageSize: 50,
  startDate: '',
  endDate: '',
})
const instruments = ref<LocalInstrument[]>([])
const listMeta = ref<LocalInstrumentMeta | null>(null)
const selected = ref<LocalInstrument | null>(null)
const chart = ref<LocalMarketChart | null>(null)
const maKeys = ref(MA_OPTIONS.map((option) => option.key))
const period = ref<MarketChartPeriod>('daily')
const showRsi = ref(true)
const showMacd = ref(true)
const loading = ref(false)
const chartLoading = ref(false)
const message = ref('')

const selectedTitle = computed(() => (
  selected.value ? `${selected.value.market} ${selected.value.code}` : '请选择股票'
))

function apiMessage(error: unknown): string {
  if (error instanceof FormulaScreenApiError) return error.message
  return '本地行情读取失败，请检查 vipdoc 数据目录后重试。'
}

async function loadInstruments(): Promise<void> {
  loading.value = true
  message.value = ''
  try {
    const response = await fetchLocalInstruments({
      vipdoc_path: form.vipdocPath.trim() || undefined,
      market: form.market,
      keyword: form.keyword.trim() || undefined,
      page: form.page,
      page_size: form.pageSize,
    })
    instruments.value = response.items
    listMeta.value = response.meta
    const current = selected.value && response.items.find(
      (item) => item.market === selected.value?.market && item.code === selected.value?.code,
    )
    selected.value = current ?? response.items[0] ?? null
    if (selected.value) await loadChart(selected.value)
    else chart.value = null
  } catch (error) {
    instruments.value = []
    listMeta.value = null
    selected.value = null
    chart.value = null
    message.value = apiMessage(error)
  } finally {
    loading.value = false
  }
}

async function loadChart(instrument = selected.value): Promise<void> {
  if (!instrument) {
    chart.value = null
    return
  }
  if (instrument.error) {
    chart.value = null
    message.value = instrument.error
    return
  }
  chartLoading.value = true
  try {
    chart.value = await fetchLocalChart({
      vipdoc_path: form.vipdocPath.trim() || undefined,
      market: instrument.market,
      code: instrument.code,
      period: period.value,
      start_date: form.startDate || undefined,
      end_date: form.endDate || undefined,
    })
    message.value = ''
  } catch (error) {
    chart.value = null
    message.value = apiMessage(error)
  } finally {
    chartLoading.value = false
  }
}

async function selectInstrument(instrument: LocalInstrument): Promise<void> {
  selected.value = instrument
  await loadChart(instrument)
}

async function setPeriod(next: MarketChartPeriod): Promise<void> {
  if (period.value === next) return
  period.value = next
  await loadChart()
}

function toggleMa(key: string): void {
  maKeys.value = maKeys.value.includes(key)
    ? maKeys.value.filter((current) => current !== key)
    : [...maKeys.value, key]
}

async function changePage(next: number): Promise<void> {
  if (!listMeta.value || next < 1 || next > listMeta.value.pages || next === form.page) return
  form.page = next
  await loadInstruments()
}

function formatPrice(value: number | null): string {
  return value === null ? '—' : value.toFixed(2)
}

onMounted(loadInstruments)
</script>

<template>
  <div class="screen-page market-data-page" data-testid="market-data-page">
    <header class="topbar">
      <a class="brand" href="/formula-screen" aria-label="Easy TDX 选股台首页"><span class="brand-mark">E</span><span><strong>Easy TDX</strong><small>选股台</small></span></a>
      <nav aria-label="主导航">
        <a class="nav-link" href="/formula-screen">公式选股</a>
        <a class="nav-link" href="/backtest">单股回测</a>
        <a class="nav-link" href="/portfolio-backtest">组合回测</a>
        <a class="nav-link" href="/strategy-fitness">策略适配性</a>
        <a class="nav-link active" href="/market-data" aria-current="page">本地行情</a>
      </nav>
      <div class="topbar-status"><span class="status-dot" aria-hidden="true"></span> 本地数据模式</div>
    </header>

    <main class="content-shell">
      <section class="page-intro">
        <div><p class="eyebrow">LOCAL MARKET DATA / CHART</p><h1>本地行情</h1><p class="intro-copy">直接浏览 vipdoc 中已经保存的行情，切换日线、月线、年线和常用技术指标。</p></div>
        <div class="intro-note"><span class="note-label">数据边界</span><strong>只读本地文件</strong><small>不会上传行情；图表指标在服务端计算</small></div>
      </section>

      <div v-if="message" class="notice error" role="alert" data-testid="market-data-message">{{ message }}</div>

      <div class="market-data-grid">
        <section class="panel local-instruments-panel" data-testid="local-instruments">
          <div class="panel-heading"><div><span class="section-kicker">01 / LOCAL FILES</span><h2>本地股票</h2></div><span class="required-hint">{{ listMeta?.total ?? 0 }} 个文件</span></div>
          <form class="market-filter-form" @submit.prevent="form.page = 1; loadInstruments()">
            <label for="market-vipdoc-path">vipdoc 目录</label>
            <input id="market-vipdoc-path" v-model="form.vipdocPath" data-testid="market-vipdoc-path" type="text" placeholder="/data/vipdoc">
            <div class="compact-fields">
              <div><label for="market-scope">市场</label><select id="market-scope" v-model="form.market" data-testid="market-scope"><option value="all">沪深 A 股</option><option value="SH">仅上海</option><option value="SZ">仅深圳</option></select></div>
              <div><label for="market-keyword">搜索代码</label><input id="market-keyword" v-model="form.keyword" data-testid="market-keyword" type="search" placeholder="例如 600000"></div>
            </div>
            <button class="secondary-button" data-testid="market-refresh" type="submit" :disabled="loading">{{ loading ? '读取中…' : '刷新本地列表' }}</button>
          </form>

          <div v-if="!instruments.length" class="inline-empty" data-testid="market-instruments-empty">{{ loading ? '正在读取本地 .day 文件…' : '没有找到可读取的沪深 A 股行情文件。' }}</div>
          <div v-else class="local-instrument-list">
            <button v-for="instrument in instruments" :key="`${instrument.market}-${instrument.code}`" class="local-instrument" :class="{ selected: selected?.market === instrument.market && selected?.code === instrument.code }" :data-testid="`instrument-${instrument.market}-${instrument.code}`" type="button" @click="selectInstrument(instrument)">
              <span class="instrument-topline"><strong>{{ instrument.code }}</strong><span class="market-pill" :class="instrument.market.toLowerCase()">{{ instrument.market }}</span></span>
              <span class="instrument-meta"><span>{{ instrument.bars ? `${instrument.bars} 根` : instrument.error ?? '无数据' }}</span><span>{{ instrument.last_close === null ? '—' : `¥${formatPrice(instrument.last_close)}` }}</span></span>
              <span class="instrument-range">{{ instrument.data_start ?? '—' }} → {{ instrument.data_end ?? '—' }}</span>
            </button>
          </div>
          <div v-if="listMeta && listMeta.pages > 1" class="pagination" data-testid="market-pagination"><button type="button" :disabled="form.page <= 1" @click="changePage(form.page - 1)">上一页</button><span>{{ form.page }} / {{ listMeta.pages }}</span><button type="button" :disabled="form.page >= listMeta.pages" @click="changePage(form.page + 1)">下一页</button></div>
        </section>

        <section class="panel market-chart-panel" data-testid="market-chart-panel">
          <div class="panel-heading"><div><span class="section-kicker">02 / CHART</span><h2>{{ selectedTitle }}</h2></div><span v-if="chart" class="required-hint">{{ chart.data_start }} → {{ chart.data_end }}</span></div>
          <template v-if="selected">
            <div class="chart-toolbar">
              <div class="period-switch" role="group" aria-label="K线周期"><button v-for="item in [{ key: 'daily', label: '日线' }, { key: 'monthly', label: '月线' }, { key: 'yearly', label: '年线' }]" :key="item.key" :class="{ active: period === item.key }" :data-testid="`chart-period-${item.key}`" type="button" @click="setPeriod(item.key as MarketChartPeriod)">{{ item.label }}</button></div>
              <div class="chart-date-range"><label for="market-chart-start">开始</label><input id="market-chart-start" v-model="form.startDate" data-testid="market-chart-start" type="date"><label for="market-chart-end">结束</label><input id="market-chart-end" v-model="form.endDate" data-testid="market-chart-end" type="date"><button class="secondary-button" data-testid="market-chart-refresh" type="button" :disabled="chartLoading" @click="loadChart()">刷新</button></div>
            </div>
            <div class="indicator-switches"><span>显示：</span><label v-for="option in MA_OPTIONS" :key="option.key"><input :data-testid="`toggle-${option.key}`" type="checkbox" :checked="maKeys.includes(option.key)" @change="toggleMa(option.key)">{{ option.label }}</label><label><input v-model="showRsi" data-testid="toggle-rsi" type="checkbox">RSI14</label><label><input v-model="showMacd" data-testid="toggle-macd" type="checkbox">MACD</label></div>
            <div v-if="chartLoading" class="chart-loading" data-testid="market-chart-loading">正在生成图表…</div>
            <MarketCandlestickChart v-else-if="chart" :candles="chart.candles" :ma-keys="maKeys" :period="period" :show-macd="showMacd" :show-rsi="showRsi" />
            <div v-else class="market-chart-empty" data-testid="market-chart-empty">暂无该股票在所选区间内的行情数据。</div>
            <div v-if="chart" class="chart-data-summary" data-testid="market-chart-summary"><span>本地日线 {{ chart.total_daily_bars }} 根</span><span>当前 {{ chart.bars }} 根{{ period === 'daily' ? '日' : period === 'monthly' ? '月' : '年' }}线</span><span>可用区间 {{ chart.available_data_start }} → {{ chart.available_data_end }}</span></div>
          </template>
          <div v-else class="market-chart-empty" data-testid="market-chart-empty">请选择股票生成 K 线图。</div>
        </section>
      </div>
    </main>
  </div>
</template>
