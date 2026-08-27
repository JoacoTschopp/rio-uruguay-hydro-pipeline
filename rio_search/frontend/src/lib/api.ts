// Cliente HTTP para `/api/*` (Fase 4, `rio_search/backend/rio_search/interfaces/api/`). Los tipos
// de acá reflejan literalmente `interfaces/api/schemas.py` -- verificados contra el servidor real
// corriendo (`curl` a cada endpoint) durante la Fase 5, no inferidos solo leyendo el código Python.
// Ningún tipo acá "inventa" campos que la API no devuelve.

export interface RunOut {
  run_id: string
  run_name: string
  experiment_id: string
  parent_run_id: string | null
  status: string
  start_time_ms: number | null
  end_time_ms: number | null
  artifact_uri: string
  tags: Record<string, string>
  params: Record<string, string>
  metrics: Record<string, number>
}

export interface SearchOut {
  search: RunOut
  trials: RunOut[]
}

export interface SearchListOut {
  searches: SearchOut[]
}

export interface RunListOut {
  runs: RunOut[]
}

export interface RunDetailOut {
  run: RunOut
  children: RunOut[]
}

export interface RunComparisonOut {
  runs: RunOut[]
  missing_run_ids: string[]
  param_diff: Record<string, Record<string, string | null>>
}

export interface MetricPointOut {
  step: number
  timestamp_ms: number
  value: number
}

export interface MetricSeriesOut {
  run_id: string
  metric: string
  points: MetricPointOut[]
}

export type JobStatus = 'queued' | 'running' | 'finished' | 'failed'

export interface JobOut {
  job_id: string
  label: string
  config_path: string
  status: JobStatus
  created_at: string
  started_at: string | null
  ended_at: string | null
  exit_code: number | null
  pid: number | null
  extra: Record<string, string>
}

export interface JobListOut {
  jobs: JobOut[]
}

export interface DatasetVersionOut {
  delta_version: number
  sha256: string
  rows: number
  fecha_min: string
  fecha_max: string
  columns: string[]
  punto_prediccion: string | null
  exported_at: string | null
}

export interface DatasetOut {
  dataset_version: DatasetVersionOut
  cache_path: string
  mode: string
}

export interface FeatureGroupOut {
  name: string
  columns: string[]
  default_on: boolean
  description: string
}

export interface FeatureCatalogOut {
  groups: FeatureGroupOut[]
}

export interface HealthResponse {
  status: string
  service: string
  version: string
}

async function getJson<T>(path: string): Promise<T> {
  const res = await fetch(path)
  if (!res.ok) {
    const body = await res.text().catch(() => '')
    throw new Error(`GET ${path} -> ${res.status} ${res.statusText}${body ? `: ${body}` : ''}`)
  }
  return (await res.json()) as T
}

export function fetchHealth(): Promise<HealthResponse> {
  return getJson('/api/health')
}

export function fetchSearches(families?: string[]): Promise<SearchListOut> {
  const qs = families && families.length > 0 ? `?families=${encodeURIComponent(families.join(','))}` : ''
  return getJson(`/api/searches${qs}`)
}

export function fetchRuns(families?: string[]): Promise<RunListOut> {
  const qs = families && families.length > 0 ? `?families=${encodeURIComponent(families.join(','))}` : ''
  return getJson(`/api/runs${qs}`)
}

export function fetchRunDetail(runId: string): Promise<RunDetailOut> {
  return getJson(`/api/runs/${encodeURIComponent(runId)}`)
}

export function fetchRunSeries(runId: string, metricName: string): Promise<MetricSeriesOut> {
  // El backend usa `{metric_name:path}` justamente para aceptar claves con `/` (test/rmse/h01,
  // time/train_total_s, §3.5/§3.12 del plan) -- no hace falta escapar los `/`, solo el resto.
  return getJson(`/api/runs/${encodeURIComponent(runId)}/series/${metricName}`)
}

export function compareRuns(runIds: string[]): Promise<RunComparisonOut> {
  return getJson(`/api/runs/compare?ids=${encodeURIComponent(runIds.join(','))}`)
}

export async function submitJob(config: string, label?: string): Promise<JobOut> {
  const res = await fetch('/api/jobs', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ config, label: label || undefined }),
  })
  if (!res.ok) {
    const body = await res.text().catch(() => '')
    throw new Error(`POST /api/jobs -> ${res.status} ${res.statusText}${body ? `: ${body}` : ''}`)
  }
  return (await res.json()) as JobOut
}

export function fetchJobs(): Promise<JobListOut> {
  return getJson('/api/jobs')
}

export function fetchJob(jobId: string): Promise<JobOut> {
  return getJson(`/api/jobs/${encodeURIComponent(jobId)}`)
}

export type RefreshMode = 'offline' | 'volume_as_is' | 'ensure_latest'

export function fetchDataset(mode: RefreshMode = 'offline'): Promise<DatasetOut> {
  return getJson(`/api/datasets?mode=${mode}`)
}

export function fetchFeatures(): Promise<FeatureCatalogOut> {
  return getJson('/api/features')
}
