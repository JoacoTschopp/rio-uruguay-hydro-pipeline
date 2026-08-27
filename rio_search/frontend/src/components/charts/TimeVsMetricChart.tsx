import { CartesianGrid, Legend, ResponsiveContainer, Scatter, ScatterChart, Tooltip, XAxis, YAxis } from 'recharts'
import { formatNumber, formatSeconds } from '../../lib/format'

export interface TimeMetricPoint {
  id: string
  label: string
  color: string
  timeSeconds: number
  metricValue: number
}

/** "Tiempo vs. metrica" (§3.9/§3.7/§3.12): frente de costo-beneficio entre trials de una
 * comparacion -- cuanto cuesta (segundos) cada punto de la metrica de calidad elegida. Un punto
 * por run, coloreado por identidad (misma paleta que el resto de graficos de Comparar). */
export function TimeVsMetricChart({ points, metricLabel }: { points: TimeMetricPoint[]; metricLabel: string }) {
  if (points.length === 0) {
    return <p style={{ color: 'var(--text-muted)' }}>Sin runs con tiempo y metrica disponibles.</p>
  }
  return (
    <ResponsiveContainer width="100%" height={320}>
      <ScatterChart margin={{ top: 8, right: 16, left: 4, bottom: 4 }}>
        <CartesianGrid stroke="var(--border)" />
        <XAxis
          type="number"
          dataKey="timeSeconds"
          name="tiempo"
          tick={{ fill: 'var(--text-muted)', fontSize: 12 }}
          axisLine={{ stroke: 'var(--border-strong)' }}
          tickLine={false}
          tickFormatter={(v: number) => formatSeconds(v)}
          label={{ value: 'tiempo de entrenamiento', position: 'insideBottom', offset: -2, fill: 'var(--text-muted)', fontSize: 12 }}
        />
        <YAxis
          type="number"
          dataKey="metricValue"
          name={metricLabel}
          tick={{ fill: 'var(--text-muted)', fontSize: 12 }}
          axisLine={{ stroke: 'var(--border-strong)' }}
          tickLine={false}
          width={64}
          label={{ value: metricLabel, angle: -90, position: 'insideLeft', fill: 'var(--text-muted)', fontSize: 12 }}
        />
        <Tooltip
          cursor={{ strokeDasharray: '3 3' }}
          contentStyle={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 6, fontSize: 12 }}
          labelStyle={{ color: 'var(--text-h)' }}
          formatter={(value: unknown, name: unknown) =>
            name === 'tiempo' ? formatSeconds(Number(value)) : formatNumber(Number(value), 4)
          }
        />
        <Legend wrapperStyle={{ fontSize: 12 }} />
        {points.map((p) => (
          <Scatter key={p.id} name={p.label} data={[p]} fill={p.color} shape="circle" isAnimationActive={false} />
        ))}
      </ScatterChart>
    </ResponsiveContainer>
  )
}
