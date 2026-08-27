export type CombineMode = 'all' | 'any' | 'at_least'
export type Universe = 'all' | 'sh' | 'sz' | 'custom'
export type FormulaMode = 'preset' | 'custom'
export type BacktestExecution = 'next_open' | 'next_close'
export type BacktestPositionMode = 'full' | 'fixed'

export interface SignalDefinition {
  id: string
  display_name: string
  description: string
}

export interface IndicatorDefinition {
  id: string
  display_name: string
  minimum_bars: number
  recommended_bars: number
  signals: SignalDefinition[]
}

export interface FormulaScreenMetadata {
  indicators: IndicatorDefinition[]
  combine_modes: { value: CombineMode; label: string }[]
  supported_markets: string[]
  supported_universe: { value: Universe; label: string }[]
  periods: { value: 'daily'; label: string }[]
  data_directory_help: string
  default_vipdoc_path?: string
}

export interface CustomParameterDefinition {
  name: string
  default: number
  minimum: number
  maximum: number
  step: number
}

export interface CustomSignalDefinition {
  id: string
  display_name: string
  description: string
}

export interface CustomFormulaMetadata {
  parameters: CustomParameterDefinition[]
  signals: CustomSignalDefinition[]
  minimum_bars: number
  warnings: string[]
}

export interface ScreenFormState {
  mode: FormulaMode
  selectedSignals: string[]
  combineMode: CombineMode
  minimumMatches: number | null
  universe: Universe
  universeFile: string
  vipdocPath: string
  workers: number
  period: 'daily'
  formulaText: string
  formulaParameters: Record<string, number>
}

export interface ScanPayload {
  selected_signals: string[]
  combine_mode: CombineMode
  minimum_matches: number | null
  universe: Universe
  universe_file: string | null
  vipdoc_path: string
  workers: number
  period: 'daily'
  formula_text: string | null
  formula_parameters: Record<string, number>
}

export interface JobState {
  job_id: string
  status: 'queued' | 'running' | 'completed' | 'failed'
  progress: number
  total_candidates: number
  total_scanned: number
  total_signals: number
  errors: number
  skipped: number
  error: string | null
}

export interface MarketSyncResult {
  total_candidates: number
  processed: number
  updated_files: number
  unchanged_files: number
  written_bars: number
  errors: number
  failure_reasons: Record<string, number>
}

export interface MarketSyncJobState {
  job_id: string
  status: 'queued' | 'running' | 'completed' | 'failed'
  progress: number
  total_candidates: number
  total_scanned: number
  errors: number
  error: string | null
  result: MarketSyncResult | null
}

export interface ScreenResult {
  market: string
  code: string
  signal_date: number
  last_close: number
  matched_signals: string[]
  match_count: number
  indicator_values: Record<string, number | null>
}

export interface ResultsMeta {
  total_candidates: number
  total_scanned: number
  total_signals: number
  errors: number
  skipped: number
  failure_reasons: Record<string, number>
  skip_reasons: Record<string, number>
}

export interface BacktestPayload {
  market: 'SH' | 'SZ'
  code: string
  vipdoc_path: string
  buy_signal: string
  sell_signal: string
  formula_text?: string | null
  formula_parameters?: Record<string, number>
  start_date?: string | null
  end_date?: string | null
  initial_cash?: number
  commission?: number
  min_commission?: number
  stamp_tax?: number
  slippage?: number
  execution?: BacktestExecution
  position_mode?: BacktestPositionMode
  fixed_size?: number | null
}

export interface BacktestEquityPoint {
  date: string
  cash: number | null
  position_value: number | null
  total: number | null
  drawdown: number | null
  drawdown_pct: number | null
}

export interface BacktestTrade {
  date: string
  direction: 'BUY' | 'SELL'
  size: number
  price: number
  commission: number
  slippage: number
  pnl: number
  cost_basis?: number
  rejected: boolean
}

export interface BacktestPosition {
  date: string
  size: number
  avg_price: number
  market_value: number
  unrealized_pnl: number
}

export interface BacktestResult {
  market: 'SH' | 'SZ'
  code: string
  bars: number
  start_date: string
  end_date: string
  buy_signal: string
  sell_signal: string
  performance: Record<string, number | null>
  equity_curve: BacktestEquityPoint[]
  trades: BacktestTrade[]
  positions: BacktestPosition[]
  configuration: Record<string, number | string | null>
  diagnostic: string | null
}

export interface BacktestJobState {
  job_id: string
  status: 'queued' | 'running' | 'completed' | 'failed'
  progress: number
  total_candidates: number
  total_scanned: number
  errors: number
  error: string | null
  result: BacktestResult | null
}
