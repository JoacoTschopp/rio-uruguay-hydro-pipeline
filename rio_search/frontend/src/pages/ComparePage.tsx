import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Link, useSearchParams } from 'react-router-dom'
import { compareRuns } from '../lib/api'
import { extractMetricByHorizon, parseHorizonMetrics } from '../lib/metrics'
import { colorForIndex } from '../lib/chartData'
import { formatNumber, formatSeconds, statusTone } from '../lib/format'
import { Badge } from '../components/ui/Badge'
import { Panel } from '../components/ui/Panel'
import { HorizonLineChart } from '../components/charts/HorizonLineChart'
import { TimeVsMetricChart, type TimeMetricPoint } from '../components/charts/TimeVsMetricChart'
import tableStyles from '../styles/table.module.css'
import styles from './ComparePage.module.css'

const TIME_METRIC_CANDIDATES = ['time/train_total_s', 'time/search_total_s', 'time/predict_test_s']

export function ComparePage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const ids = (searchParams.get('ids') ?? '').split(',').filter(Boolean)
  const [addInput, setAddInput] = useState('')
  const [split, setSplit] = useState<'test' | 'val'>('test')
  const [metricName, setMetricName] = useState('kge')
  const [timeMetric, setTimeMetric] = useState(TIME_METRIC_CANDIDATES[0])

  const { data, isLoading, error } = useQuery({
    queryKey: ['compare', ids.join(',')],
    queryFn: () => compareRuns(ids),
    enabled: ids.length > 0,
  })

  const runs = useMemo(() => data?.runs ?? [], [data])

  const tables = useMemo(
    () => runs.map((r) => ({ run: r, test: parseHorizonMetrics(r.metrics, 'test'), val: parseHorizonMetrics(r.metrics, 'val') })),
    [runs],
  )

  const metricNames = useMemo(() => {
    const set = new Set<string>()
    for (const t of tables) {
      for (const m of t.test.metricNames) set.add(m)
      for (const m of t.val.metricNames) set.add(m)
    }
    return Array.from(set).sort()
  }, [tables])
  const activeMetric = metricNames.includes(metricName) ? metricName : metricNames[0]

  const chartSeries = tables.map((t, i) => ({
    id: t.run.run_id,
    label: shortLabel(t.run.run_name),
    color: colorForIndex(i),
    values: extractMetricByHorizon(split === 'test' ? t.test : t.val, activeMetric ?? ''),
  }))

  const timeMetricKeys = useMemo(() => {
    const set = new Set<string>()
    for (const r of runs) for (const k of Object.keys(r.metrics)) if (k.startsWith('time/')) set.add(k)
    return Array.from(set).sort()
  }, [runs])

  const timePoints: TimeMetricPoint[] = tables
    .map((t, i) => {
      const time = t.run.metrics[timeMetric]
      const metricValue = t.run.metrics[`test/${activeMetric}/mean`] ?? t.run.metrics[`val/${activeMetric}/mean`]
      if (time === undefined || metricValue === undefined) return null
      return { id: t.run.run_id, label: shortLabel(t.run.run_name), color: colorForIndex(i), timeSeconds: time, metricValue }
    })
    .filter((p): p is TimeMetricPoint => p !== null)

  function updateIds(next: string[]) {
    setSearchParams(next.length > 0 ? { ids: next.join(',') } : {})
  }

  function addId() {
    const value = addInput.trim()
    if (!value || ids.includes(value)) return
    updateIds([...ids, value])
    setAddInput('')
  }

  function removeId(id: string) {
    updateIds(ids.filter((i) => i !== id))
  }

  return (
    <div className={styles.page}>
      <h1>Comparar</h1>
      <p>
        N runs seleccionados (desde Búsquedas, o pegando <code>run_id</code>s acá). Fuente:{' '}
        <code>GET /api/runs/compare?ids=…</code>.
      </p>

      <Panel title="Runs seleccionados">
        <div className={styles.idChips}>
          {ids.map((id) => (
            <span key={id} className={styles.chip}>
              <code>{id.slice(0, 10)}…</code>
              <button onClick={() => removeId(id)} aria-label="quitar">
                ×
              </button>
            </span>
          ))}
          <div className={styles.addRow}>
            <input
              placeholder="run_id a agregar"
              value={addInput}
              onChange={(e) => setAddInput(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && addId()}
            />
            <button onClick={addId}>Agregar</button>
          </div>
        </div>
        {data?.missing_run_ids && data.missing_run_ids.length > 0 && (
          <p style={{ color: 'var(--status-critical)' }}>No encontrados: {data.missing_run_ids.join(', ')}</p>
        )}
        {isLoading && <p>Cargando…</p>}
        {error && <p style={{ color: 'var(--status-critical)' }}>{(error as Error).message}</p>}
      </Panel>

      {runs.length === 0 && ids.length === 0 && (
        <Panel title="Sin runs">
          <p>
            Agregá al menos un <code>run_id</code>, o volvé a{' '}
            <Link to="/">Búsquedas</Link> y seleccioná trials con el checkbox.
          </p>
        </Panel>
      )}

      {runs.length > 0 && (
        <>
          <Panel title="Tabla comparativa">
            <div className={tableStyles.wrap}>
              <table className={tableStyles.table}>
                <thead>
                  <tr>
                    <th>run</th>
                    <th>modelo</th>
                    <th>estrategia</th>
                    <th>estado</th>
                    <th className={tableStyles.num}>test/kge/mean</th>
                    <th className={tableStyles.num}>test/rmse/mean</th>
                    <th className={tableStyles.num}>train_total_s</th>
                  </tr>
                </thead>
                <tbody>
                  {runs.map((r) => (
                    <tr key={r.run_id}>
                      <td>
                        <Link to={`/runs/${r.run_id}`}>{shortLabel(r.run_name)}</Link>
                      </td>
                      <td>{r.tags['rio_search.model'] ?? '—'}</td>
                      <td>{r.tags['rio_search.horizon_strategy'] ?? '—'}</td>
                      <td>
                        <Badge tone={statusTone(r.status)}>{r.status}</Badge>
                      </td>
                      <td className={tableStyles.num}>{formatNumber(r.metrics['test/kge/mean'], 3)}</td>
                      <td className={tableStyles.num}>{formatNumber(r.metrics['test/rmse/mean'], 1)}</td>
                      <td className={tableStyles.num}>{formatSeconds(r.metrics['time/train_total_s'])}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Panel>

          <Panel
            title="Métrica vs. horizonte"
            actions={
              <>
                <select value={split} onChange={(e) => setSplit(e.target.value as 'test' | 'val')}>
                  <option value="test">test</option>
                  <option value="val">val</option>
                </select>
                <select value={activeMetric ?? ''} onChange={(e) => setMetricName(e.target.value)}>
                  {metricNames.map((m) => (
                    <option key={m} value={m}>
                      {m}
                    </option>
                  ))}
                </select>
              </>
            }
          >
            <HorizonLineChart series={chartSeries} metricLabel={activeMetric ?? ''} />
          </Panel>

          <Panel
            title="Tiempo vs. métrica"
            actions={
              <select value={timeMetric} onChange={(e) => setTimeMetric(e.target.value)}>
                {timeMetricKeys.map((k) => (
                  <option key={k} value={k}>
                    {k}
                  </option>
                ))}
              </select>
            }
          >
            <TimeVsMetricChart points={timePoints} metricLabel={`test/${activeMetric}/mean`} />
          </Panel>

          <Panel title="Diff de configs">
            {data && Object.keys(data.param_diff).length > 0 ? (
              <div className={tableStyles.wrap}>
                <table className={tableStyles.table}>
                  <thead>
                    <tr>
                      <th>param</th>
                      {runs.map((r) => (
                        <th key={r.run_id}>{shortLabel(r.run_name)}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {Object.entries(data.param_diff).map(([param, byRun]) => (
                      <tr key={param}>
                        <td>{param}</td>
                        {runs.map((r) => (
                          <td key={r.run_id}>{byRun[r.run_id] ?? '—'}</td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <p>Los params son idénticos entre los runs seleccionados.</p>
            )}
          </Panel>
        </>
      )}
    </div>
  )
}

function shortLabel(runName: string): string {
  return runName.length > 34 ? `${runName.slice(0, 34)}…` : runName
}
