import { beforeEach, describe, expect, it, vi } from 'vitest'

import { createPortfolioBacktest, getPortfolioBacktest, getPortfolioBacktestResults } from './portfolioBacktest'

describe('portfolio backtest API', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  it('creates a job and retrieves its status and results', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(new Response(JSON.stringify({ data: { job_id: 'portfolio-1', status: 'queued' } }), { status: 202 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ data: { job_id: 'portfolio-1', status: 'completed' } }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ data: { max_positions: 3 }, meta: {} }), { status: 200 }))

    await expect(createPortfolioBacktest({
      vipdoc_path: '/data/vipdoc',
      universe: 'all',
      selected_signals: ['custom.buy'],
      combine_mode: 'any',
      minimum_matches: null,
      ranking_value: 'custom.rank',
      max_positions: 3,
      sell_signal: 'custom.sell',
    })).resolves.toEqual({ job_id: 'portfolio-1', status: 'queued' })
    await expect(getPortfolioBacktest('portfolio-1')).resolves.toEqual({ job_id: 'portfolio-1', status: 'completed' })
    await expect(getPortfolioBacktestResults('portfolio-1')).resolves.toEqual({ max_positions: 3 })
    expect(fetchMock.mock.calls.map(([url]) => url)).toEqual([
      '/api/v1/portfolio-backtests',
      '/api/v1/portfolio-backtests/portfolio-1',
      '/api/v1/portfolio-backtests/portfolio-1/results',
    ])
  })
})
