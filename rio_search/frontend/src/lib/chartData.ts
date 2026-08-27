import type { MetricPointOut } from './api'
import { HORIZON_KEYS } from './metrics'

export interface HorizonSeries {
  id: string
  label: string
  color: string
  values: Partial<Record<string, number>> // horizon -> value (solo h01..h14, sin "mean")
}

/** Une N series (una por run) en filas por horizonte, formato que Recharts espera para un
 * LineChart con varias lineas (una key por serie). El eje x son los horizontes reales (t+1..t+14),
 * no incluye "mean" -- eso se lee en la tabla, no tiene sentido en una curva vs. horizonte. */
export function mergeHorizonSeries(series: HorizonSeries[]): Array<Record<string, number | string>> {
  return HORIZON_KEYS.map((h) => {
    const row: Record<string, number | string> = { horizon: h, horizonDay: Number(h.slice(1)) }
    for (const s of series) {
      const v = s.values[h]
      if (v !== undefined) row[s.id] = v
    }
    return row
  })
}

export interface LossCurvePoint {
  step: number
  train?: number
  val?: number
}

/** Une las series `train/loss` y `val/loss` (`GET /api/runs/{id}/series/{name}`) por `step`
 * (epoch) en filas para un unico LineChart de dos lineas. */
export function mergeLossCurves(train: MetricPointOut[], val: MetricPointOut[]): LossCurvePoint[] {
  const byStep = new Map<number, LossCurvePoint>()
  for (const p of train) {
    byStep.set(p.step, { ...(byStep.get(p.step) ?? { step: p.step }), step: p.step, train: p.value })
  }
  for (const p of val) {
    byStep.set(p.step, { ...(byStep.get(p.step) ?? { step: p.step }), step: p.step, val: p.value })
  }
  return Array.from(byStep.values()).sort((a, b) => a.step - b.step)
}

/** Paleta categorica fija (dataviz skill, `references/palette.md`), asignada por indice de serie
 * -- nunca ciclada ni reordenada por filtro. */
export const SERIES_COLORS = [
  'var(--series-1)',
  'var(--series-2)',
  'var(--series-3)',
  'var(--series-4)',
  'var(--series-5)',
  'var(--series-6)',
  'var(--series-7)',
  'var(--series-8)',
]

export function colorForIndex(index: number): string {
  return SERIES_COLORS[index % SERIES_COLORS.length]
}
