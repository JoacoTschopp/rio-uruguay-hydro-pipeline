import { useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link, useParams } from 'react-router-dom'
import { fetchRunDetail, fetchRunSeries, promoteChampion, type TargetVariable } from '../lib/api'
import {
  extractMetricByHorizon,
  groupParamsBySection,
  groupRioSearchTags,
  listTimeMetrics,
  listTrainingScalars,
  parseHorizonMetrics,
  pickSplit,
} from '../lib/metrics'
import { colorForIndex } from '../lib/chartData'
import { formatDateTimeMs, formatDurationMs, formatNumber, formatTimingValue, statusTone, truncateHash } from '../lib/format'
import { Badge } from '../components/ui/Badge'
import { Panel } from '../components/ui/Panel'
import { GapNotice } from '../components/ui/GapNotice'
import { HorizonLineChart } from '../components/charts/HorizonLineChart'
import { LossCurveChart } from '../components/charts/LossCurveChart'
import tableStyles from '../styles/table.module.css'
import styles from './RunPage.module.css'

/** Tono del badge de `rio_search.veredicto` (runner.py, protocolo de busqueda): gana/empata son
 * resultado normal, pierde/descartado es lo que hace que una celda no compita mas. */
function veredictoTone(v: string): 'good' | 'warning' | 'critical' | 'neutral' {
  if (v === 'gana') return 'good'
  if (v === 'empata') return 'neutral'
  if (v === 'pierde' || v === 'descartado') return 'critical'
  return 'warning'
}

// Artefactos que `RunSearch` loguea de verdad (§3.5 del plan, verificado contra
// `application/experiments/run_search.py`: `log_artifact_dir(..., artifact_path=...)`). La API de
// la Fase 4 no expone un endpoint para listar/descargar artefactos de un run -- por eso esto es
// una lista fija informativa, no una llamada real; el `artifact_uri` de abajo es la unica
// referencia real que trae la API.
const KNOWN_ARTIFACT_PATHS = [
  { path: 'config/', desc: 'experiment.yaml tal como se corrio' },
  { path: 'split/', desc: 'split.json: fechas exactas de cada split' },
  { path: 'features/', desc: 'spec.json: columnas finales, orden, transforms' },
  { path: 'predictions/', desc: 'val.parquet / test.parquet: fecha, horizonte, observado, predicho' },
  { path: 'timings/', desc: 'timings.json: desglose completo de tiempos' },
  { path: 'model/', desc: 'checkpoint del modelo (state_dict + MLmodel minimo, Decision 039/042)' },
  { path: 'code/', desc: 'uncommitted.patch + package.zip (procedencia, §3.13)' },
]

export function RunPage() {
  const { runId = '' } = useParams()
  const queryClient = useQueryClient()
  const { data, isLoading, error } = useQuery({
    queryKey: ['run', runId],
    queryFn: () => fetchRunDetail(runId),
    enabled: runId.length > 0,
  })

  const promote = useMutation({
    mutationFn: (target: TargetVariable) => promoteChampion({ run_id: runId, target }),
    onSuccess: (champion) => {
      queryClient.invalidateQueries({ queryKey: ['champion', champion.target] })
      queryClient.invalidateQueries({ queryKey: ['forecast-latest', champion.target] })
    },
  })

  const [selectedChildId, setSelectedChildId] = useState<string | undefined>(undefined)
  const [split, setSplit] = useState<'test' | 'val'>('test')
  const [metricName, setMetricName] = useState<string>('kge')

  const testTable = useMemo(() => (data ? parseHorizonMetrics(data.run.metrics, 'test') : { metricNames: [], rows: [] }), [data])
  const valTable = useMemo(() => (data ? parseHorizonMetrics(data.run.metrics, 'val') : { metricNames: [], rows: [] }), [data])
  const hasOwnHorizonMetrics = testTable.rows.length > 0 || valTable.rows.length > 0
  const metricNames = Array.from(new Set([...testTable.metricNames, ...valTable.metricNames])).sort()
  const activeMetric = metricNames.includes(metricName) ? metricName : metricNames[0]
  const activeTable = split === 'test' ? testTable : valTable

  const lossRunId = data && data.children.length > 0 ? selectedChildId ?? data.children[0]?.run_id : runId

  const trainLoss = useQuery({
    queryKey: ['series', lossRunId, 'train/loss'],
    queryFn: () => fetchRunSeries(lossRunId as string, 'train/loss'),
    enabled: !!lossRunId && hasOwnHorizonMetrics,
  })
  const valLoss = useQuery({
    queryKey: ['series', lossRunId, 'val/loss'],
    queryFn: () => fetchRunSeries(lossRunId as string, 'val/loss'),
    enabled: !!lossRunId && hasOwnHorizonMetrics,
  })

  if (isLoading) return <p>Cargando run…</p>
  if (error) return <p style={{ color: 'var(--status-critical)' }}>{(error as Error).message}</p>
  if (!data) return null

  const { run, children } = data
  const tags = groupRioSearchTags(run.tags)
  const paramSections = groupParamsBySection(run.params)
  const timeMetrics = listTimeMetrics(run.metrics)
  const trainingScalars = listTrainingScalars(run.metrics)

  const chartSeries = [
    { id: 'val', label: 'val', color: colorForIndex(0), values: extractMetricByHorizon(valTable, activeMetric ?? '') },
    { id: 'test', label: 'test', color: colorForIndex(1), values: extractMetricByHorizon(testTable, activeMetric ?? '') },
  ].filter((s) => Object.keys(s.values).length > 0)

  const coverageRows = activeTable.rows.filter((r) => r.horizon !== 'mean' && r.values.coverage !== undefined)

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <div>
          <Link to="/">← Búsquedas</Link>
          <h1>{run.run_name}</h1>
          {(run.tags['rio_search.model'] || run.tags['rio_search.celda_id']) && (
            <p className={styles.identityLine}>
              {run.tags['rio_search.model'] && <Badge tone="neutral">{run.tags['rio_search.model']}</Badge>}
              {run.tags['rio_search.celda_id'] && (
                <span>
                  <strong>{run.tags['rio_search.celda_id']}</strong>
                  {run.tags['rio_search.nombre'] && <> — {run.tags['rio_search.nombre']}</>}
                </span>
              )}
              {run.tags['rio_search.veredicto'] && (
                <Badge tone={veredictoTone(run.tags['rio_search.veredicto'])}>{run.tags['rio_search.veredicto']}</Badge>
              )}
            </p>
          )}
          <p className={styles.subline}>
            <span className="mono">{run.run_id}</span>
            <Badge tone={statusTone(run.status)}>{run.status}</Badge>
            {run.parent_run_id && (
              <Link to={`/runs/${run.parent_run_id}`} className={styles.parentLink}>
                ver búsqueda padre
              </Link>
            )}
          </p>
        </div>
        <div className={styles.headerActions}>
          {(() => {
            const runTarget = run.tags['rio_search.target']
            const target: TargetVariable | null =
              runTarget === 'caudal' || runTarget === 'nivel' ? runTarget : null
            if (!target) {
              return (
                <button
                  disabled
                  title="Este run no tiene el tag rio_search.target (caudal|nivel) -- no parece un trial promovible."
                  className={styles.championBtn}
                >
                  Promover a campeón
                </button>
              )
            }
            return (
              <button
                disabled={promote.isPending}
                title={`POST /api/champions (PromoteChampion, Fase 6) -- fija este run como campeón de ${target} (alias champion_${target} en Unity Catalog + copia local en SQLite).`}
                className={styles.championBtn}
                onClick={() => promote.mutate(target)}
              >
                {promote.isPending
                  ? 'Promoviendo…'
                  : promote.isSuccess
                    ? `Campeón de ${target} ✓`
                    : `Promover a campeón (${target})`}
              </button>
            )
          })()}
        </div>
      </div>
      {promote.isError && (
        <p className={styles.promoteError}>{(promote.error as Error).message}</p>
      )}

      <div className={styles.grid}>
        <Panel title="Config">
          <div className={tableStyles.wrap}>
            {Object.entries(paramSections).map(([section, kv]) => (
              <div key={section} className={styles.paramSection}>
                <h3>{section}</h3>
                <table className={tableStyles.table}>
                  <tbody>
                    {Object.entries(kv).map(([k, v]) => (
                      <tr key={k}>
                        <td>{k}</td>
                        <td className={tableStyles.wrapCell}>{v}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ))}
            {Object.keys(paramSections).length === 0 && <p>Sin params.</p>}
          </div>
        </Panel>

        <Panel title="Tags">
          <TagGroup title="Dataset" tags={tags.dataset} />
          <TagGroup title="Procedencia" tags={tags.provenance} githubKey="github_url" />
          <TagGroup title="Hardware" tags={tags.hardware} />
          <TagGroup title="Otros" tags={tags.other} />
        </Panel>
      </div>

      {hasOwnHorizonMetrics ? (
        <>
          <Panel
            title="Métricas por horizonte"
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
            <div className={tableStyles.wrap}>
              <table className={tableStyles.table}>
                <thead>
                  <tr>
                    <th>horizonte</th>
                    {activeTable.metricNames.map((m) => (
                      <th key={m} className={tableStyles.num}>
                        {m}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {activeTable.rows.map((row) => (
                    <tr key={row.horizon}>
                      <td>{row.horizon}</td>
                      {activeTable.metricNames.map((m) => (
                        <td key={m} className={tableStyles.num}>
                          {formatNumber(row.values[m], 3)}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Panel>

          <Panel title="Panel de tiempos (time/*)">
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
                  {trainingScalars.map((m) => (
                    <tr key={`train-${m.key}`}>
                      <td>train/{m.key}</td>
                      <td className={tableStyles.num}>{formatNumber(m.value, 0)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {timeMetrics.length === 0 && <p>Sin métricas de tiempo en este run.</p>}
            </div>
          </Panel>

          <Panel
            title="Curva de pérdida"
            actions={
              children.length > 0 ? (
                <select value={lossRunId} onChange={(e) => setSelectedChildId(e.target.value)}>
                  {children.map((c) => (
                    <option key={c.run_id} value={c.run_id}>
                      {c.run_name}
                    </option>
                  ))}
                </select>
              ) : undefined
            }
          >
            {trainLoss.isLoading || valLoss.isLoading ? (
              <p>Cargando series…</p>
            ) : (
              <LossCurveChart train={trainLoss.data?.points ?? []} val={valLoss.data?.points ?? []} />
            )}
          </Panel>

          <Panel title="Hidrograma TEST (observado vs. predicho)">
            <GapNotice>
              La API de la Fase 4 (<code>interfaces/api/main.py</code>) no expone un endpoint para leer
              artefactos de MLflow (<code>predictions/test.parquet</code>, <code>series/*.json</code> del
              plan §3.5) -- solo expone historial de <em>metricas</em> escalares (
              <code>GET /api/runs/{'{id}'}/series/{'{name}'}</code>), que es lo que alimenta la curva de
              pérdida de arriba. Para pintar el hidrograma real hace falta un endpoint nuevo (p. ej.{' '}
              <code>GET /api/runs/{'{id}'}/artifacts/predictions/test</code>) fuera del alcance de esta
              fase (no se tocó el backend salvo el montaje de estáticos). Documentado como gap para el
              agente principal.
            </GapNotice>
          </Panel>

          <Panel title="Cobertura de splits">
            {coverageRows.length > 0 ? (
              <div className={tableStyles.wrap}>
                <table className={tableStyles.table}>
                  <thead>
                    <tr>
                      <th>horizonte</th>
                      <th className={tableStyles.num}>cobertura ({split})</th>
                    </tr>
                  </thead>
                  <tbody>
                    {coverageRows.map((r) => (
                      <tr key={r.horizon}>
                        <td>{r.horizon}</td>
                        <td className={tableStyles.num}>{formatNumber((r.values.coverage ?? 0) * 100, 1)}%</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <GapNotice>
                Sin métrica <code>{split}/coverage/hNN</code> en este run; el artefacto{' '}
                <code>split/split.json</code> (fechas exactas de cada split, §3.5) tampoco es accesible
                desde la API por el mismo motivo del hidrograma.
              </GapNotice>
            )}
          </Panel>
        </>
      ) : (
        <Panel title="Runs hijos">
          <p className={styles.searchNote}>
            Este run no trae sus propias métricas por horizonte: o es un run padre de búsqueda (agrega
            solo tiempos de búsqueda, <code>time/search_*</code>) o es un trial <code>per_horizon</code>{' '}
            cuyos horizontes viven en sus runs hijos. Runs hijos de este:
          </p>
          <div className={tableStyles.wrap}>
            <table className={tableStyles.table}>
              <thead>
                <tr>
                  <th>run</th>
                  <th>estado</th>
                  <th className={tableStyles.num}>gral/mean</th>
                  <th className={tableStyles.num}>nse/mean</th>
                  <th className={tableStyles.num}>kge/mean</th>
                  <th>inicio</th>
                </tr>
              </thead>
              <tbody>
                {children.map((c) => {
                  const gral = pickSplit(c, 'gral')
                  const nse = pickSplit(c, 'nse')
                  const kge = pickSplit(c, 'kge')
                  return (
                    <tr key={c.run_id}>
                      <td>
                        <Link to={`/runs/${c.run_id}`}>{c.run_name}</Link>
                      </td>
                      <td>
                        <Badge tone={statusTone(c.status)}>{c.status}</Badge>
                      </td>
                      <td className={tableStyles.num}>
                        {formatNumber(gral?.value, 4)}
                        {gral && <span className={styles.splitTag}>{gral.split}</span>}
                      </td>
                      <td className={tableStyles.num}>
                        {formatNumber(nse?.value, 3)}
                        {nse && <span className={styles.splitTag}>{nse.split}</span>}
                      </td>
                      <td className={tableStyles.num}>
                        {formatNumber(kge?.value, 3)}
                        {kge && <span className={styles.splitTag}>{kge.split}</span>}
                      </td>
                      <td>{formatDurationMs(c.start_time_ms, c.end_time_ms)}</td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
          {timeMetrics.length > 0 && (
            <div className={tableStyles.wrap} style={{ marginTop: 'var(--space-3)' }}>
              <table className={tableStyles.table}>
                <thead>
                  <tr>
                    <th>time/*</th>
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
        </Panel>
      )}

      <Panel title="Artefactos">
        <p>
          <span className={styles.label}>artifact_uri</span> <code className={styles.artifactUri}>{run.artifact_uri}</code>
        </p>
        <GapNotice>
          La API no expone listado ni descarga de artefactos de MLflow; esta es la lista de rutas que
          <code> RunSearch</code> loguea de verdad (leído del código, §3.5 del plan), no una llamada real.
        </GapNotice>
        <ul className={styles.artifactList}>
          {KNOWN_ARTIFACT_PATHS.map((a) => (
            <li key={a.path}>
              <code>{a.path}</code> — {a.desc}
            </li>
          ))}
        </ul>
      </Panel>

      <div className={styles.footerMeta}>
        <span>inicio: {formatDateTimeMs(run.start_time_ms)}</span>
        <span>fin: {formatDateTimeMs(run.end_time_ms)}</span>
        <span>duración: {formatDurationMs(run.start_time_ms, run.end_time_ms)}</span>
        <span>experiment_id: {run.experiment_id}</span>
      </div>
    </div>
  )
}

function TagGroup({ title, tags, githubKey }: { title: string; tags: Record<string, string>; githubKey?: string }) {
  const entries = Object.entries(tags)
  if (entries.length === 0) return null
  return (
    <div className={styles.tagGroup}>
      <h3>{title}</h3>
      <dl className={styles.tagList}>
        {entries.map(([k, v]) => (
          <div key={k} className={styles.tagRow}>
            <dt>{k}</dt>
            <dd>
              {k === githubKey ? (
                <a href={v} target="_blank" rel="noreferrer">
                  {v}
                </a>
              ) : k === 'git_sha' ? (
                <span title={v}>{truncateHash(v, 12)}</span>
              ) : (
                v
              )}
            </dd>
          </div>
        ))}
      </dl>
    </div>
  )
}
