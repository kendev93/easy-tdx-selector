import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { FormulaScreenMetadata } from '../types'
import FormulaScreenPage from './FormulaScreenPage.vue'

import * as api from '../api/formulaScreen'

vi.mock('../api/formulaScreen', async () => {
  const actual = await vi.importActual<typeof import('../api/formulaScreen')>('../api/formulaScreen')
  return { ...actual, fetchMetadata: vi.fn(), parseFormula: vi.fn(), createJob: vi.fn(), getJob: vi.fn(), getResults: vi.fn() }
})

const metadata: FormulaScreenMetadata = {
  indicators: [
    {
      id: 'indicator_three', display_name: '指标三 · 拉升准备', minimum_bars: 34, recommended_bars: 120,
      signals: [
        { id: 'indicator_three.prepare_rally', display_name: '准备拉升', description: 'VAR1 上穿 8' },
        { id: 'indicator_three.accumulation_zone', display_name: '建仓区', description: 'VARO7 < 10' },
      ],
    },
  ],
  combine_modes: [
    { value: 'all', label: '全部满足 AND' }, { value: 'any', label: '任一满足 OR' }, { value: 'at_least', label: '至少满足 N 个' },
  ],
  supported_markets: ['SH', 'SZ'],
  supported_universe: [{ value: 'all', label: '沪深全部 A 股' }],
  periods: [{ value: 'daily', label: '日线' }],
  data_directory_help: '本地目录',
}

describe('FormulaScreenPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(api.fetchMetadata).mockResolvedValue(metadata)
    vi.mocked(api.parseFormula).mockResolvedValue({
      parameters: [{ name: 'N', default: 5, minimum: 1, maximum: 10000, step: 1 }],
      signals: [{ id: 'custom.breakout', display_name: 'BREAKOUT', description: 'BREAKOUT 的最后一根 K 线输出不为 0' }],
      minimum_bars: 6,
      warnings: [],
    })
    vi.mocked(api.createJob).mockResolvedValue({ job_id: 'job-1', status: 'queued' })
    vi.mocked(api.getJob).mockResolvedValue({
      job_id: 'job-1', status: 'completed', progress: 1, total_candidates: 2, total_scanned: 2,
      total_signals: 2, errors: 0, skipped: 0, error: null,
    })
    vi.mocked(api.getResults).mockResolvedValue({
      results: [{ market: 'SH', code: '600000', signal_date: 20260824, last_close: 12.35, matched_signals: ['indicator_three.accumulation_zone'], match_count: 1, indicator_values: { 'indicator_three.varo7': 2.2 } }],
      meta: { total_candidates: 2, total_scanned: 2, total_signals: 1, errors: 0, skipped: 0, failure_reasons: {}, skip_reasons: {} },
    })
  })

  it('renders signal choices and validates an empty selection', async () => {
    const wrapper = mount(FormulaScreenPage)
    await flushPromises()

    expect(wrapper.get('[data-testid="formula-screen-page"]')).toBeTruthy()
    expect(wrapper.get('[data-testid="signal-indicator_three.prepare_rally"]')).toBeTruthy()
    await wrapper.get('[data-testid="screen-config"]').trigger('submit')
    expect(wrapper.get('[data-testid="signals-error"]').text()).toContain('至少选择')
    expect(api.createJob).not.toHaveBeenCalled()
  })

  it('submits selected signals, shows results, and keeps export controls', async () => {
    const wrapper = mount(FormulaScreenPage)
    await flushPromises()
    await wrapper.get('[data-testid="vipdoc-path"]').setValue('/data/vipdoc')
    await wrapper.get('[data-testid="signal-indicator_three.prepare_rally"]').setValue(true)
    await wrapper.get('[data-testid="signal-indicator_three.accumulation_zone"]').setValue(true)
    await wrapper.get('[data-testid="minimum-matches"]').setValue(2)
    await wrapper.get('[data-testid="screen-config"]').trigger('submit')
    await flushPromises()

    expect(api.createJob).toHaveBeenCalledWith(expect.objectContaining({
      selected_signals: ['indicator_three.prepare_rally', 'indicator_three.accumulation_zone'],
      combine_mode: 'at_least', minimum_matches: 2, vipdoc_path: '/data/vipdoc',
    }))
    expect(wrapper.get('[data-testid="results-table"]').text()).toContain('600000')
    expect(wrapper.get('[data-testid="export-json"]')).toBeTruthy()
    expect(wrapper.get('[data-testid="export-csv"]')).toBeTruthy()

    Object.defineProperty(URL, 'createObjectURL', { value: vi.fn().mockReturnValue('blob:test'), configurable: true })
    Object.defineProperty(URL, 'revokeObjectURL', { value: vi.fn(), configurable: true })
    const clickSpy = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => undefined)
    await wrapper.get('[data-testid="export-json"]').trigger('click')
    await wrapper.get('[data-testid="export-csv"]').trigger('click')
    expect(clickSpy).toHaveBeenCalledTimes(2)
    clickSpy.mockRestore()
  })

  it('shows a user-facing error when the job request fails', async () => {
    vi.mocked(api.createJob).mockRejectedValueOnce(new Error('network down'))
    const wrapper = mount(FormulaScreenPage)
    await flushPromises()
    await wrapper.get('[data-testid="vipdoc-path"]').setValue('/data/vipdoc')
    await wrapper.get('[data-testid="signal-indicator_three.prepare_rally"]').setValue(true)
    await wrapper.get('[data-testid="minimum-matches"]').setValue(1)
    await wrapper.get('[data-testid="screen-config"]').trigger('submit')
    await flushPromises()

    expect(wrapper.get('[data-testid="screen-message"]').text()).toContain('扫描失败')
  })

  it('parses a custom formula, exposes parameters, and submits the override', async () => {
    const wrapper = mount(FormulaScreenPage)
    await flushPromises()
    await wrapper.get('[data-testid="mode-custom"]').trigger('click')
    await wrapper.get('[data-testid="custom-formula"]').setValue('N:=5; BREAKOUT:CROSS(C,REF(C,N));')
    await wrapper.get('[data-testid="parse-formula"]').trigger('click')
    await flushPromises()

    expect(wrapper.get('[data-testid="custom-formula-meta"]').text()).toContain('1 个参数')
    expect(wrapper.get('[data-testid="custom-signal-custom.breakout"]')).toBeTruthy()
    await wrapper.get('[data-testid="formula-param-N"]').setValue(7)
    await wrapper.get('[data-testid="vipdoc-path"]').setValue('/data/vipdoc')
    await wrapper.get('[data-testid="combine-mode"]').setValue('any')
    await wrapper.get('[data-testid="screen-config"]').trigger('submit')
    await flushPromises()

    expect(api.parseFormula).toHaveBeenCalledWith('N:=5; BREAKOUT:CROSS(C,REF(C,N));')
    expect(api.createJob).toHaveBeenCalledWith(expect.objectContaining({
      formula_text: 'N:=5; BREAKOUT:CROSS(C,REF(C,N));',
      formula_parameters: { N: 7 },
      selected_signals: ['custom.breakout'],
    }))
  })
})
