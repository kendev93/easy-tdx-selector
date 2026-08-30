import type {
  CombineMode,
  CustomFormulaMetadata,
  FormulaScreenMetadata,
  InstrumentBoard,
  InstrumentType,
  ScanPayload,
  ScreenFormState,
  ScreenResult,
} from '../types'

export const DEFAULT_PRESET_SIGNALS = [
  'indicator_three.prepare_rally',
  'indicator_three.accumulation_zone',
]

const FORM_STORAGE_KEY = 'easy-tdx-selector.form.v1'

export function loadSavedForm(): Partial<ScreenFormState> {
  if (typeof window === 'undefined') return {}
  try {
    const raw = window.localStorage.getItem(FORM_STORAGE_KEY)
    if (!raw) return {}
    const parsed = JSON.parse(raw) as Record<string, unknown>
    if (!parsed || typeof parsed !== 'object') return {}
    const safe: Partial<ScreenFormState> = {}
    if (parsed.mode === 'preset' || parsed.mode === 'custom') safe.mode = parsed.mode
    if (Array.isArray(parsed.selectedSignals) && parsed.selectedSignals.every((value) => typeof value === 'string')) {
      safe.selectedSignals = parsed.selectedSignals as string[]
    }
    if (parsed.combineMode === 'all' || parsed.combineMode === 'any' || parsed.combineMode === 'at_least') {
      safe.combineMode = parsed.combineMode
    }
    if (typeof parsed.minimumMatches === 'number' && Number.isFinite(parsed.minimumMatches)) safe.minimumMatches = parsed.minimumMatches
    if (parsed.universe === 'all' || parsed.universe === 'sh' || parsed.universe === 'sz' || parsed.universe === 'custom') {
      safe.universe = parsed.universe
    }
    if (typeof parsed.universeFile === 'string') safe.universeFile = parsed.universeFile
    if (Array.isArray(parsed.instrumentTypes)) {
      const values = parsed.instrumentTypes.filter((value): value is InstrumentType => (
        value === 'stock' || value === 'fund' || value === 'index' || value === 'bond'
      ))
      safe.instrumentTypes = values
    }
    if (Array.isArray(parsed.boards)) {
      const values = parsed.boards.filter((value): value is InstrumentBoard => (
        value === 'main' || value === 'star' || value === 'chinext' || value === 'b_share'
        || value === 'fund' || value === 'index' || value === 'bond'
      ))
      safe.boards = values
    }
    if (typeof parsed.workers === 'number' && Number.isFinite(parsed.workers)) safe.workers = parsed.workers
    if (parsed.period === 'daily') safe.period = parsed.period
    if (typeof parsed.formulaText === 'string') safe.formulaText = parsed.formulaText
    if (parsed.formulaParameters && typeof parsed.formulaParameters === 'object') {
      const parameters = Object.fromEntries(
        Object.entries(parsed.formulaParameters).filter(([, value]) => typeof value === 'number' && Number.isFinite(value)),
      ) as Record<string, number>
      safe.formulaParameters = parameters
    }
    return safe
  } catch {
    return {}
  }
}

export function saveForm(form: ScreenFormState): void {
  if (typeof window === 'undefined') return
  try {
    window.localStorage.setItem(FORM_STORAGE_KEY, JSON.stringify(form))
  } catch {
    // Private browsing and restricted storage should not block scanning.
  }
}

export function validateScreenForm(
  form: ScreenFormState,
  customMetadata: CustomFormulaMetadata | null = null,
): Record<string, string> {
  const errors: Record<string, string> = {}
  if (form.mode === 'custom') {
    if (!form.formulaText.trim()) {
      errors.formulaText = '请输入通达信公式。'
    } else if (!customMetadata) {
      errors.formulaText = '请先点击“解析公式”，确认参数和输出信号。'
    }
    if (customMetadata) {
      for (const parameter of customMetadata.parameters) {
        const value = form.formulaParameters[parameter.name]
        if (!Number.isFinite(value) || value < parameter.minimum || value > parameter.maximum) {
          errors.formulaParameters = `参数 ${parameter.name} 必须在 ${parameter.minimum} 到 ${parameter.maximum} 之间。`
          break
        }
        if (parameter.step === 1 && !Number.isInteger(value)) {
          errors.formulaParameters = `参数 ${parameter.name} 必须是整数。`
          break
        }
      }
    }
  }
  if (form.selectedSignals.length === 0) {
    errors.selectedSignals = '至少选择一个选股条件。'
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
    workers: form.workers,
    period: form.period,
    formula_text: form.mode === 'custom' ? form.formulaText.trim() || null : null,
    formula_parameters: form.mode === 'custom' ? { ...form.formulaParameters } : {},
    ...(form.instrumentTypes.length > 0 ? { instrument_types: [...form.instrumentTypes] } : {}),
    ...(form.boards.length > 0 ? { boards: [...form.boards] } : {}),
  }
}

export function filterKnownSignals(
  selectedSignals: readonly string[],
  availableSignalIds: readonly string[],
): string[] {
  const available = new Set(availableSignalIds)
  return selectedSignals.filter((signalId) => available.has(signalId))
}

export function signalDisplayName(
  signalId: string,
  metadata: FormulaScreenMetadata | null,
  customMetadata: CustomFormulaMetadata | null = null,
): string {
  const customSignal = customMetadata?.signals.find((candidate) => candidate.id === signalId)
  if (customSignal) return customSignal.display_name
  for (const indicator of metadata?.indicators ?? []) {
    const signal = indicator.signals.find((candidate) => candidate.id === signalId)
    if (signal) return signal.display_name
  }
  return signalId
}

export function resultsToCsv(results: ScreenResult[]): string {
  const header = ['market', 'code', 'instrument_type', 'board', 'signal_date', 'last_close', 'matched_signals', 'match_count', 'indicator_values']
  const escape = (value: string): string => `"${value.replace(/"/g, '""')}"`
  const rows = results.map((result) => [
    result.market,
    result.code,
    result.instrument_type ?? '',
    result.board ?? '',
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
