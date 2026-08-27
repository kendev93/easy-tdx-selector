import { beforeEach, describe, expect, it, vi } from 'vitest'

import { createBacktest, getBacktest, getBacktestResults } from './backtest'

describe('backtest API', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  it('creates a job and retrieves its status and results', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(new Response(JSON.stringify({ data: { job_id: 'bt-1', status: 'queued' } }), { status: 202 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ data: { job_id: 'bt-1', status: 'completed' } }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ data: { code: '600000' }, meta: {} }), { status: 200 }))
    const payload = { market: 'SH' as const, code: '600000', vipdoc_path: '/data/vipdoc', buy_signal: 'custom.buy', sell_signal: 'custom.sell' }

    await expect(createBacktest(payload)).resolves.toEqual({ job_id: 'bt-1', status: 'queued' })
    await expect(getBacktest('bt-1')).resolves.toEqual({ job_id: 'bt-1', status: 'completed' })
    await expect(getBacktestResults('bt-1')).resolves.toEqual({ code: '600000' })
    expect(fetchMock.mock.calls.map(([url]) => url)).toEqual([
      '/api/v1/backtests',
      '/api/v1/backtests/bt-1',
      '/api/v1/backtests/bt-1/results',
    ])
  })
})
