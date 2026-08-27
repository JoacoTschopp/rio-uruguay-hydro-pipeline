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

// ----------------------------------------------------------------------
// Fase 6 -- Predicciones (§3.8, §3.9): campeon vigente + pronostico diario + backtest movil.
// ----------------------------------------------------------------------

export type TargetVariable = 'caudal' | 'nivel'

export interface ChampionOut {
  target: string
  run_id: string
  model_name: string
  metric_name: string
  metric_value: number
  promoted_at: string
  registered_model_name: string | null
  registered_model_version: string | null
  note: string | null
}

export interface ForecastPointOut {
  horizon: number
  target_date: string
  value: number
}

export interface ForecastOut {
  target: string
  as_of: string
  issued_at: string
  dataset_delta_version: number
  dataset_sha256: string
  champion_run_id: string
  champion_model_name: string
  device_type: string
  data_lag_days: number
  forecast_run_id: string | null
  published_path: string | null
  points: ForecastPointOut[]
}

export interface ForecastHistoryOut {
  forecasts: ForecastOut[]
}

export interface BacktestPointOut {
  forecast_run_id: string | null
  issued_at: string
  as_of: string
  horizon: number
  target_date: string
  predicted: number
  observed: number | null
  error: number | null
}

export interface BacktestOut {
  target: string
  points: BacktestPointOut[]
}

/** `404` (sin campeon promovido / sin pronosticos emitidos todavia) es un estado valido de la
 * pagina "Pronostico de hoy", no un error de red -- se devuelve `null` en vez de tirar. */
async function getJsonOrNull<T>(path: string): Promise<T | null> {
  const res = await fetch(path)
  if (res.status === 404) return null
  if (!res.ok) {
    const body = await res.text().catch(() => '')
    throw new Error(`GET ${path} -> ${res.status} ${res.statusText}${body ? `: ${body}` : ''}`)
  }
  return (await res.json()) as T
}

export function fetchChampion(target: TargetVariable): Promise<ChampionOut | null> {
  return getJsonOrNull(`/api/champions?target=${target}`)
}

export function fetchLatestForecast(target: TargetVariable): Promise<ForecastOut | null> {
  return getJsonOrNull(`/api/forecasts/latest?target=${target}`)
}

export function fetchForecastHistory(target: TargetVariable, maxResults = 20): Promise<ForecastHistoryOut> {
  return getJson(`/api/forecasts/history?target=${target}&max_results=${maxResults}`)
}

export function fetchForecastBacktest(target: TargetVariable, maxForecasts = 30): Promise<BacktestOut> {
  return getJson(`/api/forecasts/backtest?target=${target}&max_forecasts=${maxForecasts}`)
}

// ----------------------------------------------------------------------
// Fase 7 -- Research (§3.9, §3.10): biblioteca de documentos, notas por seccion, tags, BibTeX.
// ----------------------------------------------------------------------

export type DocumentType = 'paper' | 'tesis' | 'informe' | 'plantilla'

export interface DocumentOut {
  slug: string
  title: string
  authors: string[]
  year: number
  type: DocumentType
  venue: string | null
  doi_url: string | null
  tags: string[]
  file: string | null
  added_at: string
}

export interface DocumentListOut {
  documents: DocumentOut[]
}

export type LinkKind = 'decision' | 'run'

export interface LinkOut {
  kind: LinkKind
  ref: string
}

export const NOTE_SECTIONS: { key: string; label: string }[] = [
  { key: 'methodology', label: 'Metodología' },
  { key: 'models', label: 'Modelos' },
  { key: 'windows_splits', label: 'Ventanas / splits' },
  { key: 'metrics', label: 'Métricas' },
  { key: 'results', label: 'Resultados' },
  { key: 'takeaways', label: 'Qué me llevo' },
]

export interface NoteOut {
  slug: string
  sections: Record<string, string>
  links: LinkOut[]
}

export interface DocumentDetailOut {
  document: DocumentOut
  note: NoteOut
}

export interface ExportBibtexOut {
  output_path: string
  entry_count: number
  keys: string[]
}

export function fetchDocuments(): Promise<DocumentListOut> {
  return getJson('/api/research/documents')
}

export function fetchDocumentDetail(slug: string): Promise<DocumentDetailOut> {
  return getJson(`/api/research/documents/${encodeURIComponent(slug)}`)
}

export interface CreateDocumentInput {
  title: string
  authors: string // separados por ';'
  year: number
  type: DocumentType
  venue?: string
  doi_url?: string
  tags?: string // separados por ','
  slug?: string
  file?: File | null
}

export async function createDocument(input: CreateDocumentInput): Promise<DocumentDetailOut> {
  const form = new FormData()
  form.set('title', input.title)
  form.set('authors', input.authors)
  form.set('year', String(input.year))
  form.set('type', input.type)
  if (input.venue) form.set('venue', input.venue)
  if (input.doi_url) form.set('doi_url', input.doi_url)
  form.set('tags', input.tags ?? '')
  if (input.slug) form.set('slug', input.slug)
  if (input.file) form.set('file', input.file)

  const res = await fetch('/api/research/documents', { method: 'POST', body: form })
  if (!res.ok) {
    const body = await res.text().catch(() => '')
    throw new Error(`POST /api/research/documents -> ${res.status} ${res.statusText}${body ? `: ${body}` : ''}`)
  }
  return (await res.json()) as DocumentDetailOut
}

export async function updateDocumentTags(slug: string, tags: string): Promise<DocumentOut> {
  const res = await fetch(`/api/research/documents/${encodeURIComponent(slug)}/tags`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ tags }),
  })
  if (!res.ok) {
    const body = await res.text().catch(() => '')
    throw new Error(`PUT .../tags -> ${res.status} ${res.statusText}${body ? `: ${body}` : ''}`)
  }
  return (await res.json()) as DocumentOut
}

export async function updateDocumentNote(
  slug: string,
  sections: Record<string, string>,
  links: LinkOut[],
): Promise<NoteOut> {
  const res = await fetch(`/api/research/documents/${encodeURIComponent(slug)}/notes`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ sections, links }),
  })
  if (!res.ok) {
    const body = await res.text().catch(() => '')
    throw new Error(`PUT .../notes -> ${res.status} ${res.statusText}${body ? `: ${body}` : ''}`)
  }
  return (await res.json()) as NoteOut
}

export function documentFileUrl(slug: string): string {
  return `/api/research/documents/${encodeURIComponent(slug)}/file`
}

export async function exportBibtex(): Promise<ExportBibtexOut> {
  const res = await fetch('/api/research/export-bib', { method: 'POST' })
  if (!res.ok) {
    const body = await res.text().catch(() => '')
    throw new Error(`POST /api/research/export-bib -> ${res.status} ${res.statusText}${body ? `: ${body}` : ''}`)
  }
  return (await res.json()) as ExportBibtexOut
}

export async function promoteChampion(input: {
  run_id: string
  target: TargetVariable
  metric_name?: string
  note?: string
}): Promise<ChampionOut> {
  const res = await fetch('/api/champions', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(input),
  })
  if (!res.ok) {
    const body = await res.text().catch(() => '')
    throw new Error(`POST /api/champions -> ${res.status} ${res.statusText}${body ? `: ${body}` : ''}`)
  }
  return (await res.json()) as ChampionOut
}
