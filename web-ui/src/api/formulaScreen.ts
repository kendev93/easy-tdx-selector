import type {
  CustomFormulaMetadata,
  FormulaScreenMetadata,
  JobState,
  ResultsMeta,
  ScanPayload,
  ScreenResult,
} from '../types'

const API_BASE = '/api/v1/formula-screen'

interface ApiErrorPayload {
  error?: { message?: string }
}

export class FormulaScreenApiError extends Error {
  constructor(message: string, public readonly status: number) {
    super(message)
    this.name = 'FormulaScreenApiError'
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...(init?.headers ?? {}) },
  })
  const payload = (await response.json()) as T & ApiErrorPayload
  if (!response.ok) {
    throw new FormulaScreenApiError(
      payload.error?.message ?? '请求失败，请检查配置后重试。',
      response.status,
    )
  }
  return payload as T
}

export async function fetchMetadata(): Promise<FormulaScreenMetadata> {
  const payload = await request<{ data: FormulaScreenMetadata }>('/metadata')
  return payload.data
}

export async function parseFormula(formulaText: string): Promise<CustomFormulaMetadata> {
  const response = await request<{ data: CustomFormulaMetadata }>('/parse', {
    method: 'POST',
    body: JSON.stringify({ formula_text: formulaText }),
  })
  return response.data
}

export async function createJob(payload: ScanPayload): Promise<{ job_id: string; status: string }> {
  const response = await request<{ data: { job_id: string; status: string } }>('/jobs', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
  return response.data
}

export async function getJob(jobId: string): Promise<JobState> {
  const response = await request<{ data: JobState }>(`/jobs/${encodeURIComponent(jobId)}`)
  return response.data
}

export async function getResults(jobId: string): Promise<{ results: ScreenResult[]; meta: ResultsMeta }> {
  const response = await request<{ data: ScreenResult[]; meta: ResultsMeta }>(
    `/jobs/${encodeURIComponent(jobId)}/results`,
  )
  return { results: response.data, meta: response.meta }
}
