import type {
  CombineMode,
  FormulaScreenMetadata,
  ScanPayload,
  ScreenFormState,
  ScreenResult,
} from '../types'

export function validateScreenForm(form: ScreenFormState): Record<string, string> {
  const errors: Record<string, string> = {}
  if (form.selectedSignals.length === 0) {
    errors.selectedSignals = '至少选择一个选股条件。'
  }
  if (!form.vipdocPath.trim()) {
    errors.vipdocPath = '请输入通达信 vipdoc 数据目录。'
  }
  if (form.combineMode === 'at_least') {
    if (form.minimumMatches === null || !Number.isInteger(form.minimumMatches)) {
      errors.minimumMatches = '“至少满足 N 个”模式需要填写整数 N。'
    } else if (form.minimumMatches < 1 || form.minimumMatches > form.selectedSignals.length) {
      errors.minimumMatches = 'N 必须在 1 和已选择条件数量之间。'
    }
  }
  if (form.universe === 'custom' && !form.universeFile.trim()) {
    errors.universeFile = '自定义范围需要提供股票列表文件。'
  }
  return errors
}

export function buildScanPayload(form: ScreenFormState): ScanPayload {
  return {
    selected_signals: [...form.selectedSignals],
    combine_mode: form.combineMode,
    minimum_matches: form.combineMode === 'at_least' ? form.minimumMatches : null,
    universe: form.universe,
    universe_file: form.universe === 'custom' ? form.universeFile.trim() || null : null,
    vipdoc_path: form.vipdocPath.trim(),
    workers: form.workers,
    period: form.period,
  }
}

export function signalDisplayName(
  signalId: string,
  metadata: FormulaScreenMetadata | null,
): string {
  for (const indicator of metadata?.indicators ?? []) {
    const signal = indicator.signals.find((candidate) => candidate.id === signalId)
    if (signal) return signal.display_name
  }
  return signalId
}

export function resultsToCsv(results: ScreenResult[]): string {
  const header = ['market', 'code', 'signal_date', 'last_close', 'matched_signals', 'match_count', 'indicator_values']
  const escape = (value: string): string => `"${value.replace(/"/g, '""')}"`
  const rows = results.map((result) => [
    result.market,
    result.code,
    String(result.signal_date),
    String(result.last_close),
    result.matched_signals.join(', '),
    String(result.match_count),
    JSON.stringify(result.indicator_values),
  ].map(escape).join(','))
  return [header.map(escape).join(','), ...rows].join('\n')
}

export function combineModeLabel(mode: CombineMode): string {
  return { all: '全部满足 AND', any: '任一满足 OR', at_least: '至少满足 N 个' }[mode]
}
