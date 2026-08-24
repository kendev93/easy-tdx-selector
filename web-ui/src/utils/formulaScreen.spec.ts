import { describe, expect, it } from 'vitest'

import type { ScreenFormState } from '../types'
import {
  buildScanPayload,
  combineModeLabel,
  resultsToCsv,
  validateScreenForm,
} from './formulaScreen'

const baseForm = (): ScreenFormState => ({
  selectedSignals: ['indicator_three.prepare_rally', 'indicator_three.accumulation_zone'],
  combineMode: 'at_least',
  minimumMatches: 2,
  universe: 'all',
  universeFile: '',
  vipdocPath: '/data/vipdoc',
  workers: 2,
  period: 'daily',
})

describe('formula screen form helpers', () => {
  it('rejects an empty selection and invalid minimum matches', () => {
    const form = { ...baseForm(), selectedSignals: [], minimumMatches: 2 }

    expect(validateScreenForm(form)).toMatchObject({ selectedSignals: expect.any(String), minimumMatches: expect.any(String) })
  })

  it('requires a custom file and builds exact backend payload', () => {
    const form = { ...baseForm(), universe: 'custom' as const, universeFile: ' /tmp/stocks.txt ' }

    expect(validateScreenForm(form)).toEqual({})
    expect(buildScanPayload(form)).toEqual({
      selected_signals: form.selectedSignals,
      combine_mode: 'at_least',
      minimum_matches: 2,
      universe: 'custom',
      universe_file: '/tmp/stocks.txt',
      vipdoc_path: '/data/vipdoc',
      workers: 2,
      period: 'daily',
    })
  })

  it('omits minimum for AND and exports escaped CSV values', () => {
    const form = { ...baseForm(), combineMode: 'all' as const, minimumMatches: null }
    expect(buildScanPayload(form).minimum_matches).toBeNull()
    expect(combineModeLabel('any')).toBe('任一满足 OR')
    const csv = resultsToCsv([{
      market: 'SH', code: '600000', signal_date: 20260824, last_close: 12.3,
      matched_signals: ['indicator_one.main_force_entry'], match_count: 1,
      indicator_values: { 'indicator_one.var5': 1.2 },
    }])
    expect(csv).toContain('"matched_signals"')
    expect(csv).toContain('600000')
  })
})
