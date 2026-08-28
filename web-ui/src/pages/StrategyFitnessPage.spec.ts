import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { FormulaScreenMetadata, StrategyFitnessReport } from '../types'
import StrategyFitnessPage from './StrategyFitnessPage.vue'

import * as fitnessApi from '../api/strategyFitness'
import * as formulaApi from '../api/formulaScreen'

vi.mock('../api/formulaScreen', async () => {
  const actual = await vi.importActual<typeof import('../api/formulaScreen')>('../api/formulaScreen')
  return { ...actual, fetchMetadata: vi.fn(), parseFormula: vi.fn() }
})

vi.mock('../api/strategyFitness', async () => {
  const actual = await vi.importActual<typeof import('../api/strategyFitness')>('../api/strategyFitness')
  return { ...actual, createStrategyFitness: vi.fn(), getStrategyFitness: vi.fn(), getStrategyFitnessResults: vi.fn() }
})

const metadata: FormulaScreenMetadata = {
  indicators: [{
    id: 'indicator_three', display_name: '指标三 · 拉升准备', minimum_bars: 34, recommended_bars: 120,
    signals: [
      { id: 'indicator_three.prepare_rally', display_name: '准备拉升', description: 'VAR1 上穿 8' },
      { id: 'indicator_three.end_zone', display_name: '终', description: 'VAR1 > 90' },
    ],
    values: [
      { id: 'indicator_three.varo7', display_name: 'VARO7', description: '趋势值' },
      { id: 'indicator_three.varo6', display_name: 'VARO6', description: '辅助值' },
    ],
  }],
  combine_modes: [{ value: 'all', label: '全部满足' }, { value: 'any', label: '任一满足' }, { value: 'at_least', label: '至少满足' }],
  supported_markets: ['SH', 'SZ'],
  supported_universe: [{ value: 'all', label: '沪深 A 股' }, { value: 'custom', label: '自定义列表' }],
  periods: [{ value: 'daily', label: '日线' }],
  data_directory_help: '本地目录',
  default_vipdoc_path: '/data/vipdoc',
}

const phase = (name: 'train' | 'validation' | 'test', start: string, end: string, trades: number, totalReturn: number) => ({
  name, start_date: start, end_date: end, bars: 20, total_trades: trades, win_rate: 0.6,
  total_return: totalReturn, annual_return: totalReturn, max_drawdown: 0.1, sharpe: 1.2,
  profit_factor: 1.4, expectancy: 0.02, avg_holding_days: 4, diagnostic: null,
})

const report: StrategyFitnessReport = {
  universe: 'all', total_candidates: 2, processed: 2, skipped: 0, errors: 0, bars: 60,
  start_date: '2020-01-01', end_date: '2024-12-31', train_end_date: '2022-12-31', validation_end_date: '2023-12-31',
  ranking_value: 'indicator_three.varo7', train_ratio: 0.6, validation_ratio: 0.2, min_trades: 5, max_test_drawdown: 0.3,
  results: [{
    market: 'SH', code: '600000', bars: 60, data_start: '2020-01-01', data_end: '2024-12-31', suitability_score: 87.5,
    passed: true, label: 'strong', passed_checks: 7, total_checks: 8, positive_periods: 3,
    checks: [{ id: 'test_return', label: '测试期总收益为正', passed: true }],
    train: phase('train', '2020-01-01', '2022-12-31', 30, 0.42),
    validation: phase('validation', '2023-01-01', '2023-12-31', 9, 0.12),
    test: phase('test', '2024-01-01', '2024-12-31', 8, 0.08),
    failure_reason: null,
  }, {
    market: 'SZ', code: '000001', bars: 60, data_start: '2020-01-01', data_end: '2024-12-31', suitability_score: 25,
    passed: false, label: 'insufficient', passed_checks: 2, total_checks: 8, positive_periods: 1, checks: [],
    train: phase('train', '2020-01-01', '2022-12-31', 12, 0.02),
    validation: phase('validation', '2023-01-01', '2023-12-31', 1, -0.03),
    test: phase('test', '2024-01-01', '2024-12-31', 1, 0),
    failure_reason: null,
  }],
  failure_reasons: {}, diagnostic: null,
}

describe('StrategyFitnessPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(formulaApi.fetchMetadata).mockResolvedValue(metadata)
    vi.mocked(fitnessApi.createStrategyFitness).mockResolvedValue({ job_id: 'fitness-1', status: 'queued' })
    vi.mocked(fitnessApi.getStrategyFitness).mockResolvedValue({
      job_id: 'fitness-1', status: 'completed', progress: 1, total_candidates: 2, total_scanned: 2,
      errors: 0, error: null, result: null,
    })
    vi.mocked(fitnessApi.getStrategyFitnessResults).mockResolvedValue(report)
  })

  it('submits the strategy and renders compatibility scores with three phases', async () => {
    const wrapper = mount(StrategyFitnessPage)
    await flushPromises()
    await wrapper.get('[data-testid="fitness-config"]').trigger('submit')
    await flushPromises()

    expect(fitnessApi.createStrategyFitness).toHaveBeenCalledWith(expect.objectContaining({
      vipdoc_path: '/data/vipdoc', selected_signals: ['indicator_three.prepare_rally'],
      ranking_value: 'indicator_three.varo7', train_ratio: 0.6, validation_ratio: 0.2,
      min_trades: 5, max_test_drawdown: 0.3,
    }))
    expect(wrapper.get('[data-testid="fitness-results"]').text()).toContain('600000')
    expect(wrapper.get('[data-testid="fitness-results"]').text()).toContain('87.50')
    expect(wrapper.get('[data-testid="fitness-train-600000"]').text()).toContain('42.00%')
    expect(wrapper.get('[data-testid="fitness-validation-600000"]').text()).toContain('12.00%')
    expect(wrapper.get('[data-testid="fitness-test-600000"]').text()).toContain('8.00%')
  })

  it('parses a custom formula and validates an incomplete comparison rule', async () => {
    vi.mocked(formulaApi.parseFormula).mockResolvedValueOnce({
      parameters: [{ name: 'N', default: 5, minimum: 1, maximum: 100, step: 1 }],
      signals: [{ id: 'custom.buy', display_name: '买入', description: '买入' }, { id: 'custom.sell', display_name: '卖出', description: '卖出' }],
      values: [{ id: 'custom.rank', display_name: '排序', description: '排序' }],
      minimum_bars: 6, warnings: [],
    })
    const wrapper = mount(StrategyFitnessPage)
    await flushPromises()
    await wrapper.get('[data-testid="fitness-mode-custom"]').trigger('click')
    await wrapper.get('[data-testid="fitness-formula"]').setValue('N:=5; 买入:C>0; 卖出:C<0; 排序:C;')
    await wrapper.get('[data-testid="fitness-parse-formula"]').trigger('click')
    await flushPromises()
    expect((wrapper.get('[data-testid="fitness-ranking-value"]').element as HTMLSelectElement).value).toBe('custom.rank')
    await wrapper.get('[data-testid="fitness-compare-left"]').setValue('custom.rank')
    await wrapper.get('[data-testid="fitness-stop-loss-enabled"]').setValue(false)
    await wrapper.get('[data-testid="fitness-sell-signal"]').setValue('')
    await wrapper.get('[data-testid="fitness-config"]').trigger('submit')
    expect(wrapper.text()).toContain('请选择指标比较的右侧指标')
    expect(fitnessApi.createStrategyFitness).not.toHaveBeenCalled()
  })
})
