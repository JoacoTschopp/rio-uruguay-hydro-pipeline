// Parseo de las claves jerarquicas de metricas que loguea el backend (§3.5/§3.7/§3.12 del plan):
// `test/rmse/h01`, `test/rmse/mean`, `time/train_total_s`, `train/best_epoch`. Verificado contra
// runs reales de la Fase 3 (`GET /api/runs?families=bilstm`): un trial (multi_output o
// per_horizon) trae todos los horizontes agregados en su propio `metrics`, no hace falta bajar a
// los hijos para pintar la tabla/grafico de metricas por horizonte.

export const HORIZON_KEYS = ['h01', 'h02', 'h03', 'h04', 'h05', 'h06', 'h07', 'h14'] as const
export type HorizonKey = (typeof HORIZON_KEYS)[number]

export interface HorizonMetricsTable {
  /** nombres de metrica encontrados (rmse, mae, kge, ...), orden alfabetico */
  metricNames: string[]
  /** horizonte -> metrica -> valor (incluye "mean" si esta presente) */
  rows: Array<{ horizon: string; values: Record<string, number> }>
}

const HORIZON_METRIC_RE = /^(val|test)\/([a-z0-9_]+)\/(h\d{2}|mean)$/

export function parseHorizonMetrics(metrics: Record<string, number>, split: 'val' | 'test'): HorizonMetricsTable {
  const byHorizon = new Map<string, Record<string, number>>()
  const metricNames = new Set<string>()
  for (const [key, value] of Object.entries(metrics)) {
    const m = HORIZON_METRIC_RE.exec(key)
    if (!m) continue
    const [, matchedSplit, metricName, horizon] = m
    if (matchedSplit !== split) continue
    metricNames.add(metricName)
    if (!byHorizon.has(horizon)) byHorizon.set(horizon, {})
    byHorizon.get(horizon)![metricName] = value
  }
  const order = [...HORIZON_KEYS, 'mean']
  const rows = order.filter((h) => byHorizon.has(h)).map((h) => ({ horizon: h, values: byHorizon.get(h)! }))
  return { metricNames: Array.from(metricNames).sort(), rows }
}

/** Metricas `time/*` (§3.12), tal como estan (sin el prefijo), ordenadas alfabeticamente. */
export function listTimeMetrics(metrics: Record<string, number>): Array<{ key: string; value: number }> {
  return Object.entries(metrics)
    .filter(([k]) => k.startsWith('time/'))
    .map(([k, v]) => ({ key: k.slice('time/'.length), value: v }))
    .sort((a, b) => a.key.localeCompare(b.key))
}

/** Metricas de entrenamiento que no son ni horizonte ni tiempo (`train/best_epoch`, `train/epochs`). */
export function listTrainingScalars(metrics: Record<string, number>): Array<{ key: string; value: number }> {
  return Object.entries(metrics)
    .filter(([k]) => k.startsWith('train/') && k !== 'train/loss')
    .map(([k, v]) => ({ key: k.slice('train/'.length), value: v }))
    .sort((a, b) => a.key.localeCompare(b.key))
}

const PROVENANCE_TAG_KEYS = ['git_sha', 'git_branch', 'git_remote', 'git_dirty', 'github_url']
const HARDWARE_TAG_KEYS = ['device', 'device_name', 'cuda_version', 'torch_version', 'cpu', 'ram_gb', 'hostname']
const DATASET_TAG_KEYS = ['dataset_delta_version', 'dataset_sha256', 'config_sha256', 'feature_groups', 'experimental_transforms']

export interface GroupedTags {
  provenance: Record<string, string>
  hardware: Record<string, string>
  dataset: Record<string, string>
  other: Record<string, string>
}

/** Agrupa los tags `rio_search.*` (§3.5/§3.12/§3.13) en las categorias que la pagina Run muestra
 * por separado. Los tags `mlflow.*` (internos de MLflow) se descartan del todo. */
export function groupRioSearchTags(tags: Record<string, string>): GroupedTags {
  const grouped: GroupedTags = { provenance: {}, hardware: {}, dataset: {}, other: {} }
  const prefix = 'rio_search.'
  for (const [key, value] of Object.entries(tags)) {
    if (!key.startsWith(prefix)) continue
    const short = key.slice(prefix.length)
    if (PROVENANCE_TAG_KEYS.includes(short)) grouped.provenance[short] = value
    else if (HARDWARE_TAG_KEYS.includes(short)) grouped.hardware[short] = value
    else if (DATASET_TAG_KEYS.includes(short)) grouped.dataset[short] = value
    else grouped.other[short] = value
  }
  return grouped
}

/** Agrupa los params (config YAML aplanada, `dataset.horizons`, `model.params.hidden_size`, ...)
 * por su primer segmento (`dataset`, `model`, `split`, ...), igual estructura que el YAML fuente. */
export function groupParamsBySection(params: Record<string, string>): Record<string, Record<string, string>> {
  const grouped: Record<string, Record<string, string>> = {}
  for (const [key, value] of Object.entries(params)) {
    const dot = key.indexOf('.')
    const section = dot === -1 ? 'otros' : key.slice(0, dot)
    const rest = dot === -1 ? key : key.slice(dot + 1)
    if (!grouped[section]) grouped[section] = {}
    grouped[section][rest] = value
  }
  return grouped
}

export function isParentRun(run: { parent_run_id: string | null }): boolean {
  return run.parent_run_id === null
}

/** Valor de `<split>/<metric>/mean` para un run, prefiriendo test y cayendo a val -- la fase de
 * estrategias corre casi entera en VAL por protocolo (TEST se reserva para el cierre), asi que
 * la mayoria de sus trials no tienen test logueado. Devuelve tambien de que split salio el
 * numero, para mostrarlo sin mezclar ambos en silencio. Usado por SearchesPage, RunPage y
 * ComparePage -- una sola definicion, no tres copias. */
export function pickSplit(
  run: { metrics: Record<string, number> },
  metric: string,
): { value: number; split: 'test' | 'val' } | null {
  const test = run.metrics[`test/${metric}/mean`]
  if (test !== undefined) return { value: test, split: 'test' }
  const val = run.metrics[`val/${metric}/mean`]
  if (val !== undefined) return { value: val, split: 'val' }
  return null
}

/** Valores de una metrica por horizonte (sin "mean"), listos para armar una `HorizonSeries` de
 * `lib/chartData.ts`. */
export function extractMetricByHorizon(table: HorizonMetricsTable, metricName: string): Partial<Record<string, number>> {
  const out: Partial<Record<string, number>> = {}
  for (const row of table.rows) {
    if (row.horizon === 'mean') continue
    const v = row.values[metricName]
    if (v !== undefined) out[row.horizon] = v
  }
  return out
}
