import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { mergeLossCurves } from '../../lib/chartData'
import type { MetricPointOut } from '../../lib/api'
import { formatNumber } from '../../lib/format'

/** Curva de perdida (§3.9/§3.7): `train/loss` y `val/loss` por epoch, via
 * `GET /api/runs/{id}/series/{name}` (historial real de metricas de MLflow, no un artefacto). */
export function LossCurveChart({ train, val }: { train: MetricPointOut[]; val: MetricPointOut[] }) {
  const data = mergeLossCurves(train, val)
  if (data.length === 0) {
    return <p style={{ color: 'var(--text-muted)' }}>Este run no tiene curva de perdida propia (ver selector de horizonte si es una busqueda per_horizon).</p>
  }
  return (
    <ResponsiveContainer width="100%" height={280}>
      <LineChart data={data} margin={{ top: 8, right: 16, left: 4, bottom: 4 }}>
        <CartesianGrid stroke="var(--border)" vertical={false} />
        <XAxis
          dataKey="step"
          tick={{ fill: 'var(--text-muted)', fontSize: 12 }}
          axisLine={{ stroke: 'var(--border-strong)' }}
          tickLine={false}
          label={{ value: 'epoch', position: 'insideBottom', offset: -2, fill: 'var(--text-muted)', fontSize: 12 }}
        />
        <YAxis
          tick={{ fill: 'var(--text-muted)', fontSize: 12 }}
          axisLine={{ stroke: 'var(--border-strong)' }}
          tickLine={false}
          width={72}
          label={{ value: 'loss', angle: -90, position: 'insideLeft', fill: 'var(--text-muted)', fontSize: 12 }}
        />
        <Tooltip
          contentStyle={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 6, fontSize: 12 }}
          labelStyle={{ color: 'var(--text-h)' }}
          formatter={(value: unknown) => formatNumber(Number(value), 2)}
        />
        <Legend wrapperStyle={{ fontSize: 12 }} />
        <Line type="monotone" dataKey="train" name="train/loss" stroke="var(--series-1)" strokeWidth={2} dot={false} isAnimationActive={false} />
        <Line type="monotone" dataKey="val" name="val/loss" stroke="var(--series-2)" strokeWidth={2} dot={false} isAnimationActive={false} />
      </LineChart>
    </ResponsiveContainer>
  )
}
