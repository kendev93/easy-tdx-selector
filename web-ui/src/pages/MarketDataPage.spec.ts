import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { FormulaScreenApiError } from '../api/formulaScreen'
import type { LocalInstrument, LocalMarketChart } from '../types'
import * as marketApi from '../api/marketData'
import MarketDataPage from './MarketDataPage.vue'

vi.mock('../api/marketData', async () => {
  const actual = await vi.importActual<typeof import('../api/marketData')>('../api/marketData')
  return {
    ...actual,
    fetchLocalInstruments: vi.fn(),
    fetchLocalChart: vi.fn(),
    fetchStoreStatus: vi.fn(),
    createLocalImport: vi.fn(),
    createOnlineSync: vi.fn(),
    getMarketDataJob: vi.fn(),
  }
})

const instruments: LocalInstrument[] = [
  { market: 'SH', code: '600000', instrument_type: 'stock', bars: 300, data_start: '2020-01-01', data_end: '2024-12-31', last_close: 12.5, error: null },
  { market: 'SZ', code: '000001', instrument_type: 'stock', bars: 280, data_start: '2020-01-01', data_end: '2024-12-31', last_close: 10.2, error: null },
]

const chart: LocalMarketChart = {
  market: 'SH', code: '600000', period: 'daily', total_daily_bars: 300, bars: 3,
  available_data_start: '2020-01-01', available_data_end: '2024-12-31', data_start: '2024-12-27', data_end: '2024-12-31',
  candles: [
    { date: '2024-12-27', open: 10, high: 12, low: 9, close: 11, volume: 100, amount: 1100, ma: { ma5: null, ma10: null, ma20: null, ma60: null }, rsi14: null, macd: null, macd_signal: null, macd_histogram: null },
    { date: '2024-12-30', open: 11, high: 13, low: 10, close: 12, volume: 120, amount: 1440, ma: { ma5: null, ma10: null, ma20: null, ma60: null }, rsi14: null, macd: null, macd_signal: null, macd_histogram: null },
    { date: '2024-12-31', open: 12, high: 14, low: 11, close: 13, volume: 140, amount: 1820, ma: { ma5: 11.5, ma10: null, ma20: null, ma60: null }, rsi14: 68, macd: 0.5, macd_signal: 0.4, macd_histogram: 0.1 },
  ],
}

describe('MarketDataPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(marketApi.fetchLocalInstruments).mockResolvedValue({
      items: instruments,
      meta: { total: 2, page: 1, page_size: 50, pages: 1 },
    })
    vi.mocked(marketApi.fetchLocalChart).mockResolvedValue(chart)
    vi.mocked(marketApi.fetchStoreStatus).mockResolvedValue({
      database_path: '/data/market/market.duckdb',
      schema_version: 1,
      instrument_count: 2,
      bar_count: 580,
      data_start: '2020-01-01',
      data_end: '2024-12-31',
      last_local_import_at: null,
      last_online_sync_at: null,
    })
  })

  it('lists local instruments and loads daily, monthly, and yearly charts', async () => {
    const wrapper = mount(MarketDataPage)
    await flushPromises()

    expect(wrapper.get('[data-testid="local-instruments"]').text()).toContain('600000')
    await wrapper.get('[data-testid="instrument-SH-600000"]').trigger('click')
    await flushPromises()

    expect(marketApi.fetchLocalChart).toHaveBeenCalledWith(expect.objectContaining({ market: 'SH', code: '600000', period: 'daily' }))
    expect(wrapper.get('[data-testid="market-candlestick-chart"]')).toBeTruthy()
    expect(wrapper.get('[data-testid="market-chart-summary"]').text()).toContain('2024-12-31')

    await wrapper.get('[data-testid="chart-period-monthly"]').trigger('click')
    await flushPromises()
    await wrapper.get('[data-testid="chart-period-yearly"]').trigger('click')
    await flushPromises()

    expect(marketApi.fetchLocalChart).toHaveBeenLastCalledWith(expect.objectContaining({ period: 'yearly' }))
    expect(wrapper.get('[data-testid="market-chart-panel"]').text()).toContain('MA5')
  })

  it('shows a user-facing error when the local directory cannot be read', async () => {
    vi.mocked(marketApi.fetchLocalInstruments).mockRejectedValueOnce(new FormulaScreenApiError('vipdoc 路径无效', 422))
    const wrapper = mount(MarketDataPage)
    await flushPromises()

    expect(wrapper.get('[data-testid="market-data-message"]').text()).toContain('vipdoc 路径无效')
    expect(wrapper.get('[data-testid="market-chart-empty"]').text()).toContain('请选择品种')
  })

  it('imports local vipdoc data and refreshes the DuckDB status', async () => {
    vi.mocked(marketApi.createLocalImport).mockResolvedValue({ job_id: 'local-1', status: 'queued' })
    vi.mocked(marketApi.getMarketDataJob).mockResolvedValue({
      job_id: 'local-1', status: 'completed', progress: 1, total_candidates: 1,
      total_scanned: 1, errors: 0, error: null, result: null,
    })
    const wrapper = mount(MarketDataPage)
    await flushPromises()

    await wrapper.get('[data-testid="market-import-local"]').trigger('click')
    await flushPromises()

    expect(marketApi.createLocalImport).toHaveBeenCalledWith({
      vipdoc_path: '/data/vipdoc', universe: 'all',
    })
    expect(marketApi.getMarketDataJob).toHaveBeenCalledWith('local-1')
    expect(marketApi.fetchStoreStatus).toHaveBeenCalledTimes(2)
  })

  it('sends the configured market-data scope to local import', async () => {
    vi.mocked(marketApi.createLocalImport).mockResolvedValue({ job_id: 'local-2', status: 'queued' })
    vi.mocked(marketApi.getMarketDataJob).mockResolvedValue({
      job_id: 'local-2', status: 'completed', progress: 1, total_candidates: 1,
      total_scanned: 1, errors: 0, error: null, result: null,
    })
    const wrapper = mount(MarketDataPage)
    await flushPromises()

    await wrapper.get('[data-testid="market-sync-universe"]').setValue('sh')
    await wrapper.get('[data-testid="market-sync-type-stock"]').setValue(true)
    await wrapper.get('[data-testid="market-sync-board-main"]').setValue(true)
    await wrapper.get('[data-testid="market-import-local"]').trigger('click')
    await flushPromises()

    expect(marketApi.createLocalImport).toHaveBeenCalledWith({
      vipdoc_path: '/data/vipdoc',
      universe: 'sh',
      instrument_types: ['stock'],
      boards: ['main'],
    })
  })
})
