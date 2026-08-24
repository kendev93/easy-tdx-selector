<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'

import { createJob, fetchMetadata, FormulaScreenApiError, getJob, getResults } from '../api/formulaScreen'
import type { FormulaScreenMetadata, JobState, ResultsMeta, ScreenFormState, ScreenResult } from '../types'
import { buildScanPayload, resultsToCsv, signalDisplayName, validateScreenForm } from '../utils/formulaScreen'

const metadata = ref<FormulaScreenMetadata | null>(null)
const form = reactive<ScreenFormState>({
  selectedSignals: [],
  combineMode: 'at_least',
  minimumMatches: 2,
  universe: 'all',
  universeFile: '',
  vipdocPath: '',
  workers: 2,
  period: 'daily',
})
const errors = ref<Record<string, string>>({})
const message = ref('')
const loading = ref(false)
const job = ref<JobState | null>(null)
const results = ref<ScreenResult[]>([])
const resultMeta = ref<ResultsMeta | null>(null)

const progressPercent = computed(() => Math.round((job.value?.progress ?? 0) * 100))
const canSubmit = computed(() => !loading.value && metadata.value !== null)

function toggleSignal(signalId: string, checked: boolean): void {
  const next = new Set(form.selectedSignals)
  if (checked) next.add(signalId)
  else next.delete(signalId)
  form.selectedSignals = [...next]
  if (errors.value.selectedSignals) errors.value = { ...errors.value, selectedSignals: '' }
}

function apiMessage(error: unknown): string {
  if (error instanceof FormulaScreenApiError) return error.message
  return '扫描失败，请检查后端服务、数据目录和配置后重试。'
}

async function pollUntilFinished(jobId: string): Promise<void> {
  for (;;) {
    const state = await getJob(jobId)
    job.value = state
    if (state.status === 'completed') {
      const payload = await getResults(jobId)
      results.value = payload.results
      resultMeta.value = payload.meta
      message.value = `扫描完成：命中 ${payload.meta.total_signals} 个条件，得到 ${payload.results.length} 只股票。`
      return
    }
    if (state.status === 'failed') throw new Error(state.error ?? '扫描任务失败')
    await new Promise((resolve) => window.setTimeout(resolve, 250))
  }
}

async function submit(): Promise<void> {
  errors.value = validateScreenForm(form)
  message.value = ''
  if (Object.values(errors.value).some(Boolean)) return

  loading.value = true
  results.value = []
  resultMeta.value = null
  try {
    const created = await createJob(buildScanPayload(form))
    job.value = {
      job_id: created.job_id,
      status: 'queued',
      progress: 0,
      total_candidates: 0,
      total_scanned: 0,
      total_signals: 0,
      errors: 0,
      skipped: 0,
      error: null,
    }
    await pollUntilFinished(created.job_id)
  } catch (error) {
    message.value = apiMessage(error)
  } finally {
    loading.value = false
  }
}

function download(filename: string, content: string, type: string): void {
  const url = URL.createObjectURL(new Blob([content], { type }))
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  link.click()
  URL.revokeObjectURL(url)
}

function exportJson(): void {
  download('formula-screen-results.json', JSON.stringify({ summary: resultMeta.value, results: results.value }, null, 2), 'application/json')
}

function exportCsv(): void {
  download('formula-screen-results.csv', resultsToCsv(results.value), 'text/csv;charset=utf-8')
}

onMounted(async () => {
  try {
    metadata.value = await fetchMetadata()
  } catch (error) {
    message.value = apiMessage(error)
  }
})
</script>

<template>
  <div class="screen-page" data-testid="formula-screen-page">
    <header class="topbar">
      <a class="brand" href="/formula-screen" aria-label="Easy TDX 选股台首页">
        <span class="brand-mark">E</span>
        <span><strong>Easy TDX</strong><small>选股台</small></span>
      </a>
      <nav aria-label="主导航">
        <a class="nav-link active" href="/formula-screen" aria-current="page">公式选股</a>
      </nav>
      <div class="topbar-status"><span class="status-dot" aria-hidden="true"></span> 本地数据模式</div>
    </header>

    <main class="content-shell">
      <section class="page-intro">
        <div>
          <p class="eyebrow">FORMULA SCREEN / DAILY</p>
          <h1>公式选股</h1>
          <p class="intro-copy">把通达信条件拆成可组合的信号，扫描已完成的日线 K 线。</p>
        </div>
        <div class="intro-note"><span class="note-label">扫描范围</span><strong>SH / SZ A 股</strong><small>ETF、基金、指数与债券已排除</small></div>
      </section>

      <div v-if="message" class="notice" :class="{ error: !message.includes('完成') }" role="alert" data-testid="screen-message">
        <span>{{ message }}</span>
      </div>

      <div class="workspace-grid">
        <form class="config-panel panel" data-testid="screen-config" @submit.prevent="submit">
          <div class="panel-heading">
            <div><span class="section-kicker">01 / CONFIGURE</span><h2>扫描配置</h2></div>
            <span class="required-hint">* 必填</span>
          </div>

          <fieldset class="form-section">
            <legend>数据源</legend>
            <label for="vipdoc-path">vipdoc 数据目录 <span class="required">*</span></label>
            <input id="vipdoc-path" v-model="form.vipdocPath" data-testid="vipdoc-path" type="text" placeholder="例如 ~/new_tdx/vipdoc" autocomplete="off">
            <p class="helper">{{ metadata?.data_directory_help ?? '请输入包含 sh/lday 和 sz/lday 的通达信 vipdoc 目录。' }}</p>
            <p v-if="errors.vipdocPath" class="field-error">{{ errors.vipdocPath }}</p>
          </fieldset>

          <fieldset class="form-section">
            <legend>扫描范围</legend>
            <label for="universe">市场范围</label>
            <select id="universe" v-model="form.universe" data-testid="universe">
              <option v-for="item in metadata?.supported_universe ?? []" :key="item.value" :value="item.value">{{ item.label }}</option>
            </select>
            <template v-if="form.universe === 'custom'">
              <label for="universe-file">股票列表文件 <span class="required">*</span></label>
              <input id="universe-file" v-model="form.universeFile" data-testid="universe-file" type="text" placeholder="每行 SH 600000 或 SZ 000001">
              <p v-if="errors.universeFile" class="field-error">{{ errors.universeFile }}</p>
            </template>
          </fieldset>

          <fieldset class="form-section signal-section">
            <legend>选择信号 <span class="legend-count">{{ form.selectedSignals.length }} selected</span></legend>
            <p v-if="errors.selectedSignals" class="field-error" data-testid="signals-error">{{ errors.selectedSignals }}</p>
            <div v-if="!metadata" class="skeleton-list" aria-label="正在加载信号"></div>
            <div v-for="indicator in metadata?.indicators ?? []" :key="indicator.id" class="indicator-block">
              <div class="indicator-heading"><strong>{{ indicator.display_name }}</strong><small>建议预热 {{ indicator.recommended_bars }} 根 · 最少 {{ indicator.minimum_bars }} 根</small></div>
              <label v-for="signal in indicator.signals" :key="signal.id" class="signal-option" :for="signal.id">
                <input :id="signal.id" :data-testid="`signal-${signal.id}`" type="checkbox" :checked="form.selectedSignals.includes(signal.id)" @change="toggleSignal(signal.id, ($event.target as HTMLInputElement).checked)">
                <span class="fake-checkbox" aria-hidden="true"></span>
                <span class="signal-copy"><strong>{{ signal.display_name }}</strong><small>{{ signal.description }}</small></span>
              </label>
            </div>
          </fieldset>

          <fieldset class="form-section">
            <legend>条件组合</legend>
            <label for="combine-mode">组合方式</label>
            <select id="combine-mode" v-model="form.combineMode" data-testid="combine-mode">
              <option v-for="mode in metadata?.combine_modes ?? []" :key="mode.value" :value="mode.value">{{ mode.label }}</option>
            </select>
            <template v-if="form.combineMode === 'at_least'">
              <label for="minimum-matches">最少满足条件数 <span class="required">*</span></label>
              <input id="minimum-matches" v-model.number="form.minimumMatches" data-testid="minimum-matches" type="number" min="1" :max="Math.max(form.selectedSignals.length, 1)">
              <p v-if="errors.minimumMatches" class="field-error">{{ errors.minimumMatches }}</p>
            </template>
          </fieldset>

          <fieldset class="form-section compact-fields">
            <div><label for="workers">并发进程数</label><input id="workers" v-model.number="form.workers" data-testid="workers" type="number" min="1" max="32"></div>
            <div><label for="period">周期</label><select id="period" v-model="form.period" data-testid="period"><option value="daily">日线</option></select></div>
          </fieldset>

          <button class="primary-button" data-testid="start-scan" type="submit" :disabled="!canSubmit">
            <span v-if="loading" class="spinner" aria-hidden="true"></span>
            {{ loading ? '扫描中…' : '开始扫描' }}
          </button>
          <p class="privacy-note">数据在本机读取，页面不会上传行情文件。</p>
        </form>

        <section class="results-panel panel" data-testid="results-panel" aria-live="polite">
          <div class="panel-heading results-heading">
            <div><span class="section-kicker">02 / RESULTS</span><h2>扫描结果</h2></div>
            <div class="export-actions"><button type="button" data-testid="export-json" :disabled="results.length === 0" @click="exportJson">导出 JSON</button><button type="button" data-testid="export-csv" :disabled="results.length === 0" @click="exportCsv">导出 CSV</button></div>
          </div>

          <div class="metrics-strip">
            <div><span>进度</span><strong data-testid="progress-value">{{ progressPercent }}%</strong></div>
            <div><span>已扫描</span><strong data-testid="scanned-count">{{ job?.total_scanned ?? 0 }}<small>/ {{ job?.total_candidates ?? 0 }}</small></strong></div>
            <div><span>命中条件</span><strong class="positive" data-testid="signal-count">{{ resultMeta?.total_signals ?? job?.total_signals ?? 0 }}</strong></div>
            <div><span>失败 / 跳过</span><strong data-testid="error-count">{{ resultMeta?.errors ?? job?.errors ?? 0 }} / {{ resultMeta?.skipped ?? job?.skipped ?? 0 }}</strong></div>
          </div>
          <div class="progress-track" aria-label="扫描进度"><span :style="{ width: `${progressPercent}%` }"></span></div>

          <div v-if="results.length === 0" class="empty-state" data-testid="empty-results">
            <div class="empty-icon" aria-hidden="true">/</div>
            <h3>{{ loading ? '正在读取本地行情…' : '还没有扫描结果' }}</h3>
            <p>{{ loading ? '完成后会在这里显示命中的股票与指标值。' : '在左侧选择信号并开始一次扫描。' }}</p>
          </div>
          <div v-else class="table-wrap">
            <table data-testid="results-table">
              <caption class="sr-only">公式选股结果</caption>
              <thead><tr><th>市场</th><th>代码</th><th>信号日期</th><th>最新收盘</th><th>命中条件</th><th>指标值</th></tr></thead>
              <tbody>
                <tr v-for="result in results" :key="`${result.market}-${result.code}`">
                  <td><span class="market-pill" :class="result.market.toLowerCase()">{{ result.market }}</span></td>
                  <td><strong class="code">{{ result.code }}</strong></td>
                  <td class="muted-code">{{ result.signal_date }}</td>
                  <td><strong>{{ result.last_close.toFixed(2) }}</strong></td>
                  <td><div class="signal-tags"><span v-for="signal in result.matched_signals" :key="signal" class="signal-tag">{{ signalDisplayName(signal, metadata) }}</span><small>{{ result.match_count }} 条</small></div></td>
                  <td><div class="value-list"><span v-for="(value, name) in result.indicator_values" :key="name"><b>{{ name.split('.').at(-1) }}</b> {{ value === null ? '—' : value.toFixed(2) }}</span></div></td>
                </tr>
              </tbody>
            </table>
          </div>
          <div v-if="resultMeta && resultMeta.errors > 0" class="failure-summary" data-testid="failure-summary">
            <strong>失败摘要</strong><span v-for="(count, reason) in resultMeta.failure_reasons" :key="reason">{{ reason }} · {{ count }}</span>
          </div>
        </section>
      </div>
    </main>
  </div>
</template>
