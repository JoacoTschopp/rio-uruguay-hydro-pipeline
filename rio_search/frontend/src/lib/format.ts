// Formateo compartido por las paginas (Fase 5). Nada de esto le pega a la red.

export function formatSeconds(value: number | undefined | null): string {
  if (value === undefined || value === null || Number.isNaN(value)) return '—'
  if (value < 1) return `${(value * 1000).toFixed(0)} ms`
  if (value < 60) return `${value.toFixed(2)} s`
  const minutes = Math.floor(value / 60)
  const seconds = value - minutes * 60
  if (minutes < 60) return `${minutes}m ${seconds.toFixed(0).padStart(2, '0')}s`
  const hours = Math.floor(minutes / 60)
  const remMinutes = minutes - hours * 60
  return `${hours}h ${remMinutes.toString().padStart(2, '0')}m`
}

export function formatNumber(value: number | undefined | null, digits = 4): string {
  if (value === undefined || value === null || Number.isNaN(value)) return '—'
  return value.toLocaleString('es-UY', { maximumFractionDigits: digits, minimumFractionDigits: 0 })
}

export function formatDateTimeMs(ms: number | null | undefined): string {
  if (ms === null || ms === undefined) return '—'
  return new Date(ms).toLocaleString('es-UY', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

export function formatDurationMs(startMs: number | null, endMs: number | null): string {
  if (startMs === null || endMs === null) return '—'
  return formatSeconds((endMs - startMs) / 1000)
}

export function truncateHash(hash: string | undefined | null, length = 10): string {
  if (!hash) return '—'
  return hash.length > length ? `${hash.slice(0, length)}…` : hash
}

export function statusTone(status: string): 'good' | 'warning' | 'critical' | 'serious' {
  const s = status.toUpperCase()
  if (s === 'FINISHED' || s === 'FINALIZED') return 'good'
  if (s === 'RUNNING' || s === 'SCHEDULED') return 'warning'
  if (s === 'FAILED' || s === 'KILLED') return 'critical'
  return 'serious'
}

export function jobStatusTone(status: string): 'good' | 'warning' | 'critical' {
  if (status === 'finished') return 'good'
  if (status === 'failed') return 'critical'
  return 'warning' // queued | running
}

/** Formatea un valor de `time/*` (§3.12) segun el sufijo de su clave: `_ms` ya viene en
 * milisegundos, `_s` en segundos, cualquier otra cosa (p. ej. `search_trials`, un conteo) se
 * muestra como numero simple. */
export function formatTimingValue(key: string, value: number): string {
  if (key.endsWith('_ms')) return `${formatNumber(value, 3)} ms`
  if (key.endsWith('_s')) return formatSeconds(value)
  return formatNumber(value, 2)
}
