import { useEffect, useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Link, useSearchParams } from 'react-router-dom'
import { compareRuns, fetchSearches, type RunOut } from '../lib/api'

/** Familia por defecto cuando se entra a Comparar sin `ids` en la URL, y cuantos trials
 * precargar (los primeros N tal como los devuelve la busqueda, sin reordenar). */
const DEFAULT_COMPARE_FAMILY = 'fase_estrategias'
const DEFAULT_COMPARE_COUNT = 6
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

  // Sin ids en la URL: precargar los primeros DEFAULT_COMPARE_COUNT trials de la busqueda mas
  // reciente de DEFAULT_COMPARE_FAMILY, en vez de pedirle al usuario que arme la seleccion a
  // mano. Solo se dispara cuando faltan ids -- si ya hay una seleccion (propia o de Busquedas),
  // esta consulta ni corre.
  const { data: defaultSearches } = useQuery({
    queryKey: ['searches', DEFAULT_COMPARE_FAMILY],
    queryFn: () => fetchSearches([DEFAULT_COMPARE_FAMILY]),
    enabled: ids.length === 0,
  })

  useEffect(() => {
    if (ids.length > 0) return
    const latest = defaultSearches?.searches[0]
    if (!latest) return
    const defaultIds = latest.trials.slice(0, DEFAULT_COMPARE_COUNT).map((t) => t.run_id)
    if (defaultIds.length > 0) setSearchParams({ ids: defaultIds.join(',') })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [defaultSearches, ids.length])

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

  // "mejores resultados": el run con menor G-RAL (es una perdida, menor=mejor) y el de mayor NSE
  // (eficiencia, mayor=mejor) entre los seleccionados, resaltados en la tabla resumen. Cada
  // celda prefiere test/ y cae a val/ si el run no tiene test evaluado (la fase de estrategias
  // corre casi entera en VAL por protocolo: TEST se reserva para el cierre) -- pickSplit deja
  // registrado de que split salio el numero, para no mezclar silenciosamente ambos.
  const bestGralRunId = useMemo(() => bestBy(runs, 'gral', 'min'), [runs])
  const bestNseRunId = useMemo(() => bestBy(runs, 'nse', 'max'), [runs])

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
                    <th className={tableStyles.num}>gral/mean</th>
                    <th className={tableStyles.num}>nse/mean</th>
                    <th className={tableStyles.num}>kge/mean</th>
                    <th className={tableStyles.num}>rmse/mean</th>
                    <th className={tableStyles.num}>train_total_s</th>
                  </tr>
                </thead>
                <tbody>
                  {runs.map((r) => {
                    const gral = pickSplit(r, 'gral')
                    const nse = pickSplit(r, 'nse')
                    const kge = pickSplit(r, 'kge')
                    const rmse = pickSplit(r, 'rmse')
                    return (
                      <tr key={r.run_id}>
                        <td>
                          <Link to={`/runs/${r.run_id}`}>{shortLabel(r.run_name)}</Link>
                        </td>
                        <td>{r.tags['rio_search.model'] ?? '—'}</td>
                        <td>{r.tags['rio_search.horizon_strategy'] ?? '—'}</td>
                        <td>
                          <Badge tone={statusTone(r.status)}>{r.status}</Badge>
                        </td>
                        <td className={`${tableStyles.num} ${r.run_id === bestGralRunId ? styles.bestCell : ''}`}>
                          {formatNumber(gral?.value, 4)}
                          {gral && <span className={styles.splitTag}>{gral.split}</span>}
                          {r.run_id === bestGralRunId && <Badge tone="good">mejor</Badge>}
                        </td>
                        <td className={`${tableStyles.num} ${r.run_id === bestNseRunId ? styles.bestCell : ''}`}>
                          {formatNumber(nse?.value, 3)}
                          {nse && <span className={styles.splitTag}>{nse.split}</span>}
                          {r.run_id === bestNseRunId && <Badge tone="good">mejor</Badge>}
                        </td>
                        <td className={tableStyles.num}>
                          {formatNumber(kge?.value, 3)}
                          {kge && <span className={styles.splitTag}>{kge.split}</span>}
                        </td>
                        <td className={tableStyles.num}>
                          {formatNumber(rmse?.value, 1)}
                          {rmse && <span className={styles.splitTag}>{rmse.split}</span>}
                        </td>
                        <td className={tableStyles.num}>{formatSeconds(r.metrics['time/train_total_s'])}</td>
                      </tr>
                    )
                  })}
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

/** Valor de `<split>/<metric>/mean` para un run, prefiriendo test y cayendo a val -- la fase
 * de estrategias corre en VAL por protocolo, asi que la mayoria de sus trials no tienen test.
 * Devuelve tambien de que split salio, para mostrarlo y no mezclar silenciosamente ambos. */
function pickSplit(r: RunOut, metric: string): { value: number; split: 'test' | 'val' } | null {
  const test = r.metrics[`test/${metric}/mean`]
  if (test !== undefined) return { value: test, split: 'test' }
  const val = r.metrics[`val/${metric}/mean`]
  if (val !== undefined) return { value: val, split: 'val' }
  return null
}

/** id del run con el mejor valor de `metric` entre los pasados ('min' para perdidas como
 * G-RAL, 'max' para eficiencias como NSE), via pickSplit; null si ninguno lo tiene logueado. */
function bestBy(runs: RunOut[], metric: string, dir: 'min' | 'max'): string | null {
  let bestId: string | null = null
  let bestValue = dir === 'min' ? Infinity : -Infinity
  for (const r of runs) {
    const picked = pickSplit(r, metric)
    if (!picked) continue
    if ((dir === 'min' && picked.value < bestValue) || (dir === 'max' && picked.value > bestValue)) {
      bestValue = picked.value
      bestId = r.run_id
    }
  }
  return bestId
}
