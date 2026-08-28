import { beforeEach, describe, expect, it, vi } from 'vitest'

import { createStrategyFitness, getStrategyFitness, getStrategyFitnessResults } from './strategyFitness'

describe('strategy fitness API', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  it('creates a job and retrieves its status and report', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(new Response(JSON.stringify({ data: { job_id: 'fitness-1', status: 'queued' } }), { status: 202 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ data: { job_id: 'fitness-1', status: 'completed' } }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ data: { results: [] }, meta: {} }), { status: 200 }))

    await expect(createStrategyFitness({
      vipdoc_path: '/data/vipdoc', universe: 'all', selected_signals: ['custom.buy'],
      combine_mode: 'any', minimum_matches: null, ranking_value: 'custom.rank',
      sell_signal: 'custom.sell', stop_loss_pct: 0.08,
    })).resolves.toEqual({ job_id: 'fitness-1', status: 'queued' })
    await expect(getStrategyFitness('fitness-1')).resolves.toEqual({ job_id: 'fitness-1', status: 'completed' })
    await expect(getStrategyFitnessResults('fitness-1')).resolves.toEqual({ results: [] })
    expect(fetchMock.mock.calls.map(([url]) => url)).toEqual([
      '/api/v1/strategy-fitness',
      '/api/v1/strategy-fitness/fitness-1',
      '/api/v1/strategy-fitness/fitness-1/results',
    ])
  })
})
