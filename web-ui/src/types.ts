export type CombineMode = 'all' | 'any' | 'at_least'
export type Universe = 'all' | 'sh' | 'sz' | 'custom'
export type FormulaMode = 'preset' | 'custom'
export type BacktestExecution = 'next_open' | 'next_close'
export type BacktestPositionMode = 'full' | 'fixed'
export type PortfolioRankOrder = 'asc' | 'desc'
export type PortfolioRebalanceFrequency = 'daily' | 'weekly' | 'monthly'
export type PortfolioSellValueOperator = 'gte' | 'lte'
export type PortfolioCompareOperator = 'gt' | 'gte' | 'lt' | 'lte'

export interface SignalDefinition {
  id: string
  display_name: string
  description: string
}

export interface ValueDefinition {
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
  values?: ValueDefinition[]
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
  values?: ValueDefinition[]
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

export interface PortfolioBacktestPayload {
  vipdoc_path: string
  universe: Universe
  universe_file?: string | null
  selected_signals: string[]
  combine_mode: CombineMode
  minimum_matches: number | null
  ranking_value: string
  rank_order?: PortfolioRankOrder
  max_positions: number
  rebalance_frequency?: PortfolioRebalanceFrequency
  formula_text?: string | null
  formula_parameters?: Record<string, number>
  sell_signal?: string | null
  stop_loss_pct?: number | null
  take_profit_pct?: number | null
  sell_value?: string | null
  sell_value_operator?: PortfolioSellValueOperator | null
  sell_value_threshold?: number | null
  compare_left_value?: string | null
  compare_operator?: PortfolioCompareOperator | null
  compare_right_value?: string | null
  start_date?: string | null
  end_date?: string | null
  initial_cash?: number
  commission?: number
  min_commission?: number
  stamp_tax?: number
  slippage?: number
  execution?: BacktestExecution
}

export interface PortfolioBacktestJobState {
  job_id: string
  status: 'queued' | 'running' | 'completed' | 'failed'
  progress: number
  total_candidates: number
  total_scanned: number
  errors: number
  error: string | null
  result: PortfolioBacktestResult | null
}

export interface PortfolioEquityPoint {
  date: string
  cash: number
  position_value: number
  total: number
  positions_count: number
  drawdown: number
  drawdown_pct: number
}

export interface PortfolioTrade {
  date: string
  signal_date: string
  market: 'SH' | 'SZ'
  code: string
  direction: 'BUY' | 'SELL'
  size: number
  price: number
  commission: number
  stamp_tax: number
  slippage: number
  pnl: number
  cost_basis: number
  reason: string
  rejected: boolean
}

export interface PortfolioHolding {
  market: 'SH' | 'SZ'
  code: string
  size: number
  entry_price: number
  close: number
  unrealized_pnl: number
}

export interface PortfolioState {
  date: string
  cash: number
  position_value: number
  total: number
  positions_count: number
  holdings: PortfolioHolding[]
}

export interface PortfolioRankingCandidate {
  rank: number
  market: 'SH' | 'SZ'
  code: string
  score: number
  selected: boolean
}

export interface PortfolioRankingEvent {
  date: string
  slots_available: number
  ranking_value: string
  candidates: PortfolioRankingCandidate[]
}

export interface PortfolioBacktestResult {
  universe: Universe
  total_candidates: number
  processed: number
  skipped: number
  errors: number
  bars: number
  start_date: string
  end_date: string
  max_positions: number
  ranking_value: string
  rank_order: PortfolioRankOrder
  performance: Record<string, number | null>
  equity_curve: PortfolioEquityPoint[]
  trades: PortfolioTrade[]
  states: PortfolioState[]
  ranking_events: PortfolioRankingEvent[]
  failure_reasons: Record<string, number>
  diagnostic: string | null
}

export type FitnessLabel = 'strong' | 'watch' | 'weak' | 'insufficient'

export interface StrategyFitnessPayload extends Omit<PortfolioBacktestPayload, 'max_positions' | 'rebalance_frequency'> {
  train_ratio?: number
  validation_ratio?: number
  min_trades?: number
  max_test_drawdown?: number
}

export interface FitnessPhaseMetrics {
  name: 'train' | 'validation' | 'test'
  start_date: string
  end_date: string
  bars: number
  total_trades: number
  win_rate: number | null
  total_return: number | null
  annual_return: number | null
  max_drawdown: number | null
  sharpe: number | null
  profit_factor: number | null
  expectancy: number | null
  avg_holding_days: number | null
  diagnostic: string | null
}

export interface StrategyFitnessCheck {
  id: string
  label: string
  passed: boolean
}

export interface StrategyFitnessResult {
  market: 'SH' | 'SZ'
  code: string
  bars: number
  data_start: string
  data_end: string
  suitability_score: number
  passed: boolean
  label: FitnessLabel
  passed_checks: number
  total_checks: number
  positive_periods: number
  checks: StrategyFitnessCheck[]
  train: FitnessPhaseMetrics
  validation: FitnessPhaseMetrics
  test: FitnessPhaseMetrics
  failure_reason: string | null
}

export interface StrategyFitnessReport {
  universe: Universe
  total_candidates: number
  processed: number
  skipped: number
  errors: number
  bars: number
  start_date: string
  end_date: string
  train_end_date: string
  validation_end_date: string
  ranking_value: string
  train_ratio: number
  validation_ratio: number
  min_trades: number
  max_test_drawdown: number
  results: StrategyFitnessResult[]
  failure_reasons: Record<string, number>
  diagnostic: string | null
}

export interface StrategyFitnessJobState {
  job_id: string
  status: 'queued' | 'running' | 'completed' | 'failed'
  progress: number
  total_candidates: number
  total_scanned: number
  errors: number
  error: string | null
  result: StrategyFitnessReport | null
}
