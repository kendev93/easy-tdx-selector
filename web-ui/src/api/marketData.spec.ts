import { beforeEach, describe, expect, it, vi } from 'vitest'

import { fetchLocalChart, fetchLocalInstruments } from './marketData'

describe('market data API', () => {
  beforeEach(() => vi.restoreAllMocks())

  it('fetches paginated local instruments and chart data', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(new Response(JSON.stringify({
        data: [{ market: 'SH', code: '600000', bars: 300, data_start: '2020-01-01', data_end: '2024-12-31', last_close: 12.5, error: null }],
        meta: { total: 1, page: 1, page_size: 20, pages: 1 },
      }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({
        data: { market: 'SH', code: '600000', period: 'monthly', total_daily_bars: 300, bars: 12, available_data_start: '2020-01-01', available_data_end: '2024-12-31', data_start: '2024-01-31', data_end: '2024-12-31', candles: [] },
      }), { status: 200 }))

    await expect(fetchLocalInstruments({ vipdoc_path: '/data/vipdoc', market: 'SH', keyword: '600', page: 1, page_size: 20 })).resolves.toMatchObject({ meta: { total: 1 } })
    await expect(fetchLocalChart({ vipdoc_path: '/data/vipdoc', market: 'SH', code: '600000', period: 'monthly', start_date: '2024-01-01', end_date: '2024-12-31' })).resolves.toMatchObject({ period: 'monthly', code: '600000' })

    expect(fetchMock.mock.calls.map(([url]) => url)).toEqual([
      '/api/v1/market-data/local/instruments?vipdoc_path=%2Fdata%2Fvipdoc&market=SH&keyword=600&page=1&page_size=20',
      '/api/v1/market-data/local/SH/600000/bars?vipdoc_path=%2Fdata%2Fvipdoc&period=monthly&start_date=2024-01-01&end_date=2024-12-31',
    ])
  })

  it('surfaces local-data API errors', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce(new Response(JSON.stringify({ error: {} }), { status: 422 }))

    await expect(fetchLocalInstruments()).rejects.toMatchObject({
      name: 'FormulaScreenApiError',
      message: '请求失败，请检查本地行情目录后重试。',
      status: 422,
    })
  })
})
