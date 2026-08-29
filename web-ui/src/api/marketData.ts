import { FormulaScreenApiError } from './formulaScreen'
import type {
  LocalInstrument,
  LocalInstrumentMeta,
  LocalMarketChart,
  LocalMarketScope,
  MarketChartPeriod,
} from '../types'

const API_BASE = '/api/v1/market-data'

interface ApiErrorPayload {
  error?: { message?: string }
}

async function request<T>(url: string): Promise<T> {
  const response = await fetch(url, { headers: { 'Content-Type': 'application/json' } })
  const payload = (await response.json()) as T & ApiErrorPayload
  if (!response.ok) {
    throw new FormulaScreenApiError(
      payload.error?.message ?? '请求失败，请检查本地行情目录后重试。',
      response.status,
    )
  }
  return payload as T
}

export interface LocalInstrumentQuery {
  vipdoc_path?: string
  market?: LocalMarketScope
  keyword?: string
  page?: number
  page_size?: number
}

export async function fetchLocalInstruments(
  query: LocalInstrumentQuery = {},
): Promise<{ items: LocalInstrument[]; meta: LocalInstrumentMeta }> {
  const params = new URLSearchParams()
  if (query.vipdoc_path) params.set('vipdoc_path', query.vipdoc_path)
  if (query.market) params.set('market', query.market)
  if (query.keyword) params.set('keyword', query.keyword)
  if (query.page) params.set('page', String(query.page))
  if (query.page_size) params.set('page_size', String(query.page_size))
  const suffix = params.toString()
  const response = await request<{ data: LocalInstrument[]; meta: LocalInstrumentMeta }>(
    `${API_BASE}/local/instruments${suffix ? `?${suffix}` : ''}`,
  )
  return { items: response.data, meta: response.meta }
}

export interface LocalChartQuery {
  vipdoc_path?: string
  market: 'SH' | 'SZ'
  code: string
  period?: MarketChartPeriod
  start_date?: string
  end_date?: string
}

export async function fetchLocalChart(query: LocalChartQuery): Promise<LocalMarketChart> {
  const params = new URLSearchParams()
  if (query.vipdoc_path) params.set('vipdoc_path', query.vipdoc_path)
  if (query.period) params.set('period', query.period)
  if (query.start_date) params.set('start_date', query.start_date)
  if (query.end_date) params.set('end_date', query.end_date)
  const suffix = params.toString()
  const response = await request<{ data: LocalMarketChart }>(
    `${API_BASE}/local/${query.market}/${encodeURIComponent(query.code)}/bars${suffix ? `?${suffix}` : ''}`,
  )
  return response.data
}
