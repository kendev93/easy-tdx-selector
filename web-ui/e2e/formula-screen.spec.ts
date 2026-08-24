import { test, expect } from '@playwright/test'

const metadata = {
  indicators: [{
    id: 'indicator_three', display_name: '指标三 · 拉升准备', minimum_bars: 34, recommended_bars: 120,
    signals: [
      { id: 'indicator_three.prepare_rally', display_name: '准备拉升', description: 'VAR1 上穿 8' },
      { id: 'indicator_three.accumulation_zone', display_name: '建仓区', description: 'VARO7 < 10' },
    ],
  }],
  combine_modes: [{ value: 'all', label: '全部满足 AND' }, { value: 'any', label: '任一满足 OR' }, { value: 'at_least', label: '至少满足 N 个' }],
  supported_markets: ['SH', 'SZ'], supported_universe: [{ value: 'all', label: '沪深全部 A 股' }],
  periods: [{ value: 'daily', label: '日线' }], data_directory_help: '本地目录',
}

test('user can configure a formula scan, view results, and export them', async ({ page }) => {
  await page.route('**/api/v1/formula-screen/metadata', (route) => route.fulfill({ json: { data: metadata } }))
  await page.route('**/api/v1/formula-screen/jobs', (route) => route.fulfill({ status: 202, json: { data: { job_id: 'e2e-job', status: 'queued' } } }))
  await page.route('**/api/v1/formula-screen/jobs/e2e-job', (route) => route.fulfill({ json: { data: { job_id: 'e2e-job', status: 'completed', progress: 1, total_candidates: 1, total_scanned: 1, total_signals: 1, errors: 0, skipped: 0, error: null } } }))
  await page.route('**/api/v1/formula-screen/jobs/e2e-job/results', (route) => route.fulfill({ json: { data: [{ market: 'SH', code: '600000', signal_date: 20260824, last_close: 12.35, matched_signals: ['indicator_three.accumulation_zone'], match_count: 1, indicator_values: { 'indicator_three.varo7': 2.2 } }], meta: { total_candidates: 1, total_scanned: 1, total_signals: 1, errors: 0, skipped: 0, failure_reasons: {}, skip_reasons: {} } } }))

  await page.goto('/formula-screen')
  await page.getByTestId('vipdoc-path').fill('/tmp/vipdoc')
  await page.getByTestId('signal-indicator_three.prepare_rally').check()
  await page.getByTestId('signal-indicator_three.accumulation_zone').check()
  await page.getByTestId('minimum-matches').fill('2')
  await page.getByTestId('start-scan').click()

  await expect(page.getByTestId('results-table')).toContainText('600000')
  await expect(page.getByTestId('export-json')).toBeEnabled()
  await expect(page.getByTestId('export-csv')).toBeEnabled()
})
