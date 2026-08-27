import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { mergeHorizonSeries, type HorizonSeries } from '../../lib/chartData'
import { formatNumber } from '../../lib/format'

/** "Metrica vs. horizonte" (§3.9/§3.7 del plan): una linea por run/trial, eje x = horizonte
 * (t+1..t+14), eje y = la metrica elegida. Usado tanto en la pagina Run (una sola serie, val vs
 * test se pintan como dos series) como en Comparar (una serie por run seleccionado). */
export function HorizonLineChart({ series, metricLabel }: { series: HorizonSeries[]; metricLabel: string }) {
  const data = mergeHorizonSeries(series)
  if (series.length === 0) {
    return <p style={{ color: 'var(--text-muted)' }}>Sin series para graficar.</p>
  }
  return (
    <ResponsiveContainer width="100%" height={320}>
      <LineChart data={data} margin={{ top: 8, right: 16, left: 4, bottom: 4 }}>
        <CartesianGrid stroke="var(--border)" vertical={false} />
        <XAxis
          dataKey="horizon"
          tick={{ fill: 'var(--text-muted)', fontSize: 12 }}
          axisLine={{ stroke: 'var(--border-strong)' }}
          tickLine={false}
          label={{ value: 'horizonte', position: 'insideBottom', offset: -2, fill: 'var(--text-muted)', fontSize: 12 }}
        />
        <YAxis
          tick={{ fill: 'var(--text-muted)', fontSize: 12 }}
          axisLine={{ stroke: 'var(--border-strong)' }}
          tickLine={false}
          width={64}
          label={{ value: metricLabel, angle: -90, position: 'insideLeft', fill: 'var(--text-muted)', fontSize: 12 }}
        />
        <Tooltip
          contentStyle={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 6, fontSize: 12 }}
          labelStyle={{ color: 'var(--text-h)' }}
          formatter={(value: unknown) => formatNumber(Number(value), 4)}
        />
        {series.length > 1 && <Legend wrapperStyle={{ fontSize: 12 }} />}
        {series.map((s) => (
          <Line
            key={s.id}
            type="monotone"
            dataKey={s.id}
            name={s.label}
            stroke={s.color}
            strokeWidth={2}
            dot={{ r: 3 }}
            connectNulls
            isAnimationActive={false}
          />
        ))}
      </LineChart>
    </ResponsiveContainer>
  )
}
