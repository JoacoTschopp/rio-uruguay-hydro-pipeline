import { useEffect, useRef, useState, type ReactNode } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import {
  fetchChampion,
  fetchForecastBacktest,
  fetchForecastHistory,
  fetchLatestForecast,
  fetchRunDetail,
  runForecast,
  type TargetVariable,
} from '../lib/api'
import { listTimeMetrics } from '../lib/metrics'
import { formatNumber, formatTimingValue, truncateHash } from '../lib/format'
import { useJobLog } from '../lib/useJobLog'
import { Badge } from '../components/ui/Badge'
import { Panel } from '../components/ui/Panel'
import { GapNotice } from '../components/ui/GapNotice'
import tableStyles from '../styles/table.module.css'
import styles from './ForecastPage.module.css'

const TARGETS: { value: TargetVariable; label: string }[] = [
  { value: 'caudal', label: 'caudal' },
  { value: 'nivel', label: 'nivel' },
]

function formatIso(iso: string | null | undefined): string {
  if (!iso) return '—'
  const parsed = new Date(iso)
  if (Number.isNaN(parsed.getTime())) return iso
  return parsed.toLocaleString('es-UY', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

export function ForecastPage() {
  const [target, setTarget] = useState<TargetVariable>('caudal')
  const [predicting, setPredicting] = useState(false)
  const [predictError, setPredictError] = useState<string | null>(null)
  const [activeJobId, setActiveJobId] = useState<string | undefined>(undefined)
  const logBoxRef = useRef<HTMLPreElement>(null)
  const queryClient = useQueryClient()

  const champion = useQuery({ queryKey: ['champion', target], queryFn: () => fetchChampion(target) })
  const latest = useQuery({ queryKey: ['forecast-latest', target], queryFn: () => fetchLatestForecast(target) })
  const history = useQuery({
    queryKey: ['forecast-history', target],
    queryFn: () => fetchForecastHistory(target, 20),
  })
  const backtest = useQuery({
    queryKey: ['forecast-backtest', target],
    queryFn: () => fetchForecastBacktest(target, 30),
  })
  // `time/*` (dataset_refresh_s, model_load_s, preprocess_s, predict_s, total_s, §3.12) viven
  // en el run corto de MLflow (`daily_forecast`), no en el `Forecast` en si -- se leen del mismo
  // endpoint que ya usa la pagina Run (`GET /api/runs/{id}`), sin duplicar esa logica acá.
  const forecastRunId = latest.data?.forecast_run_id ?? undefined
  const forecastRun = useQuery({
    queryKey: ['run', forecastRunId],
    queryFn: () => fetchRunDetail(forecastRunId as string),
    enabled: !!forecastRunId,
  })
  const timeMetrics = forecastRun.data ? listTimeMetrics(forecastRun.data.run.metrics) : []

  const { lines: logLines, done: logDone } = useJobLog(activeJobId)

  useEffect(() => {
    if (logBoxRef.current) logBoxRef.current.scrollTop = logBoxRef.current.scrollHeight
  }, [logLines])

  useEffect(() => {
    if (!logDone) return
    // El job termino (finished o failed, useJobLog no distingue) -- refresca lo que "Predecir
    // hoy" pudo haber cambiado: el pronostico vigente, el historial y el backtest. El campeon no
    // cambia (este boton nunca reentrena, §3.8) asi que esa query no hace falta invalidarla.
    queryClient.invalidateQueries({ queryKey: ['forecast-latest', target] })
    queryClient.invalidateQueries({ queryKey: ['forecast-history', target] })
    queryClient.invalidateQueries({ queryKey: ['forecast-backtest', target] })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [logDone])

  async function handlePredictToday() {
    setPredicting(true)
    setPredictError(null)
    try {
      const job = await runForecast(target)
      setActiveJobId(job.job_id)
    } catch (e) {
      setPredictError((e as Error).message)
    } finally {
      setPredicting(false)
    }
  }

  const chartData = latest.data
    ? [...latest.data.points]
        .sort((a, b) => a.horizon - b.horizon)
        .map((p) => ({ horizon: `t+${p.horizon}`, valor: p.value, fecha: p.target_date }))
    : []

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <h1>Pronóstico de hoy</h1>
        <label className={styles.targetLabel}>
          target
          <select value={target} onChange={(e) => setTarget(e.target.value as TargetVariable)}>
            {TARGETS.map((t) => (
              <option key={t.value} value={t.value}>
                {t.label}
              </option>
            ))}
          </select>
        </label>
        <button
          className={styles.predictBtn}
          onClick={handlePredictToday}
          disabled={predicting || champion.data == null}
          title={champion.data == null ? 'Necesita un campeón promovido para este target' : undefined}
        >
          {predicting ? 'Lanzando…' : 'Predecir hoy'}
        </button>
      </div>
      <p>
        Abanico t+1…t+14 emitido por el campeón vigente (<code>IssueDailyForecast</code>, §3.8 del plan). El botón
        &quot;Predecir hoy&quot; corre <code>rio-search predict run</code> con el campeón vigente — <strong>nunca
        reentrena</strong>, usa el mejor modelo ya buscado hasta que se promueva un campeón nuevo. Se emite
        también solo por CLI/Task Scheduler (06:30 Montevideo) si preferís no usar el botón.
      </p>
      {predictError && <p className={styles.error}>{predictError}</p>}

      {activeJobId && (
        <Panel title={`Log en vivo — job ${activeJobId}`}>
          <pre ref={logBoxRef} className={styles.log}>
            {logLines.length === 0 ? '(esperando líneas…)' : logLines.join('\n')}
          </pre>
          {logDone && <Badge tone="neutral">stream cerrado — pronóstico actualizado abajo</Badge>}
        </Panel>
      )}

      <Panel title="Campeón vigente">
        {champion.isLoading && <p>Cargando…</p>}
        {champion.error && <p style={{ color: 'var(--status-critical)' }}>{(champion.error as Error).message}</p>}
        {champion.data === null && !champion.isLoading && (
          <GapNotice>
            Sin campeón promovido para <code>{target}</code>. Fijalo con{' '}
            <code>rio-search champions set --run &lt;run_id&gt; --target {target}</code> o desde el botón
            &quot;Promover a campeón&quot; en la página de un run.
          </GapNotice>
        )}
        {champion.data && (
          <div className={styles.summaryGrid}>
            <Item
              label="run_id"
              value={<Link to={`/runs/${champion.data.run_id}`}>{truncateHash(champion.data.run_id, 16)}</Link>}
            />
            <Item label="modelo" value={champion.data.model_name} />
            <Item
              label={champion.data.metric_name}
              value={formatNumber(champion.data.metric_value, 4)}
            />
            <Item label="promovido" value={formatIso(champion.data.promoted_at)} />
            <Item
              label="registrado en UC"
              value={
                champion.data.registered_model_name
                  ? `${champion.data.registered_model_name} v${champion.data.registered_model_version}`
                  : '—'
              }
            />
            {champion.data.note && (
              <Item label="nota" value={<Badge tone="warning">{champion.data.note}</Badge>} />
            )}
          </div>
        )}
      </Panel>

      <Panel title="Pronóstico vigente">
        {latest.isLoading && <p>Cargando…</p>}
        {latest.error && <p style={{ color: 'var(--status-critical)' }}>{(latest.error as Error).message}</p>}
        {latest.data === null && !latest.isLoading && (
          <GapNotice>
            Sin pronósticos emitidos todavía para <code>{target}</code>. Corré{' '}
            <code>rio-search predict run --target {target}</code> una vez que haya un campeón promovido.
          </GapNotice>
        )}
        {latest.data && (
          <>
            <div className={styles.summaryGrid}>
              <Item label="as_of" value={latest.data.as_of} />
              <Item label="data_lag_days" value={String(latest.data.data_lag_days)} />
              <Item label="dataset_delta_version" value={String(latest.data.dataset_delta_version)} />
              <Item
                label="champion_run_id"
                value={<Link to={`/runs/${latest.data.champion_run_id}`}>{truncateHash(latest.data.champion_run_id, 16)}</Link>}
              />
              <Item label="device" value={<Badge tone="neutral">{latest.data.device_type}</Badge>} />
              <Item label="emitido" value={formatIso(latest.data.issued_at)} />
              <Item
                label="forecast_run_id (daily_forecast)"
                value={
                  latest.data.forecast_run_id ? (
                    <Link to={`/runs/${latest.data.forecast_run_id}`}>{truncateHash(latest.data.forecast_run_id, 16)}</Link>
                  ) : (
                    '—'
                  )
                }
              />
              <Item label="publicado en Volume" value={latest.data.published_path ?? 'no (sin --publish)'} />
            </div>

            <ResponsiveContainer width="100%" height={280}>
              <LineChart data={chartData} margin={{ top: 8, right: 16, left: 4, bottom: 4 }}>
                <CartesianGrid stroke="var(--border)" vertical={false} />
                <XAxis
                  dataKey="horizon"
                  tick={{ fill: 'var(--text-muted)', fontSize: 12 }}
                  axisLine={{ stroke: 'var(--border-strong)' }}
                  tickLine={false}
                />
                <YAxis
                  tick={{ fill: 'var(--text-muted)', fontSize: 12 }}
                  axisLine={{ stroke: 'var(--border-strong)' }}
                  tickLine={false}
                  width={64}
                  label={{ value: target, angle: -90, position: 'insideLeft', fill: 'var(--text-muted)', fontSize: 12 }}
                />
                <Tooltip
                  contentStyle={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 6, fontSize: 12 }}
                  labelStyle={{ color: 'var(--text-h)' }}
                  formatter={(value: unknown) => formatNumber(Number(value), 2)}
                />
                <Legend wrapperStyle={{ fontSize: 12 }} />
                <Line
                  type="monotone"
                  dataKey="valor"
                  name={target}
                  stroke="var(--series-1)"
                  strokeWidth={2}
                  dot={{ r: 4 }}
                  isAnimationActive={false}
                />
              </LineChart>
            </ResponsiveContainer>

            <div className={tableStyles.wrap}>
              <table className={tableStyles.table}>
                <thead>
                  <tr>
                    <th>horizonte</th>
                    <th>fecha objetivo</th>
                    <th className={tableStyles.num}>valor</th>
                  </tr>
                </thead>
                <tbody>
                  {[...latest.data.points]
                    .sort((a, b) => a.horizon - b.horizon)
                    .map((p) => (
                      <tr key={p.horizon}>
                        <td>t+{p.horizon}</td>
                        <td>{p.target_date}</td>
                        <td className={tableStyles.num}>{formatNumber(p.value, 2)}</td>
                      </tr>
                    ))}
                </tbody>
              </table>
            </div>
          </>
        )}
      </Panel>

      <Panel title="Panel de tiempos (time/*, run de daily_forecast)">
        {!forecastRunId && <p>Sin pronóstico vigente todavía.</p>}
        {forecastRunId && forecastRun.isLoading && <p>Cargando…</p>}
        {forecastRunId && timeMetrics.length > 0 && (
          <div className={tableStyles.wrap}>
            <table className={tableStyles.table}>
              <thead>
                <tr>
                  <th>métrica</th>
                  <th className={tableStyles.num}>valor</th>
                </tr>
              </thead>
              <tbody>
                {timeMetrics.map((m) => (
                  <tr key={m.key}>
                    <td>{m.key}</td>
                    <td className={tableStyles.num}>{formatTimingValue(m.key, m.value)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {forecastRunId && !forecastRun.isLoading && timeMetrics.length === 0 && (
          <p>Sin métricas de tiempo en el run <code>{truncateHash(forecastRunId, 16)}</code>.</p>
        )}
      </Panel>

      <Panel title="Backtest reciente">
        {backtest.isLoading && <p>Cargando…</p>}
        {backtest.error && <p style={{ color: 'var(--status-critical)' }}>{(backtest.error as Error).message}</p>}
        {backtest.data && backtest.data.points.length === 0 && <p>Sin pronósticos recientes para comparar.</p>}
        {backtest.data && backtest.data.points.length > 0 && (
          <div className={tableStyles.wrap}>
            <table className={tableStyles.table}>
              <thead>
                <tr>
                  <th>emitido</th>
                  <th>as_of</th>
                  <th>horizonte</th>
                  <th>fecha objetivo</th>
                  <th className={tableStyles.num}>predicho</th>
                  <th className={tableStyles.num}>observado</th>
                  <th className={tableStyles.num}>error</th>
                </tr>
              </thead>
              <tbody>
                {backtest.data.points.map((p, i) => (
                  <tr key={`${p.forecast_run_id ?? i}-${p.horizon}`}>
                    <td>{formatIso(p.issued_at)}</td>
                    <td>{p.as_of}</td>
                    <td>t+{p.horizon}</td>
                    <td>{p.target_date}</td>
                    <td className={tableStyles.num}>{formatNumber(p.predicted, 2)}</td>
                    <td className={tableStyles.num}>
                      {p.observed === null ? <Badge tone="neutral">pendiente</Badge> : formatNumber(p.observed, 2)}
                    </td>
                    <td className={tableStyles.num}>{p.error === null ? '—' : formatNumber(p.error, 2)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Panel>

      <Panel title="Historial de pronósticos">
        {history.isLoading && <p>Cargando…</p>}
        {history.data && history.data.forecasts.length === 0 && <p>Sin pronósticos emitidos todavía.</p>}
        {history.data && history.data.forecasts.length > 0 && (
          <div className={tableStyles.wrap}>
            <table className={tableStyles.table}>
              <thead>
                <tr>
                  <th>emitido</th>
                  <th>as_of</th>
                  <th>device</th>
                  <th className={tableStyles.num}>dataset_delta_version</th>
                  <th>champion_run_id</th>
                </tr>
              </thead>
              <tbody>
                {history.data.forecasts.map((f) => (
                  <tr key={f.issued_at}>
                    <td>{formatIso(f.issued_at)}</td>
                    <td>{f.as_of}</td>
                    <td>
                      <Badge tone="neutral">{f.device_type}</Badge>
                    </td>
                    <td className={tableStyles.num}>{f.dataset_delta_version}</td>
                    <td>
                      <Link to={`/runs/${f.champion_run_id}`}>{truncateHash(f.champion_run_id, 16)}</Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Panel>
    </div>
  )
}

function Item({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className={styles.item}>
      <span className={styles.itemLabel}>{label}</span>
      <span>{value}</span>
    </div>
  )
}
