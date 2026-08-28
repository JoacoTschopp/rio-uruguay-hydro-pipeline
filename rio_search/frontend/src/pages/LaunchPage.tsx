import { useEffect, useRef, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { fetchJobs, submitJob, type JobOut } from '../lib/api'
import { formatDateTimeMs, jobStatusTone } from '../lib/format'
import { useJobLog } from '../lib/useJobLog'
import { Badge } from '../components/ui/Badge'
import { Panel } from '../components/ui/Panel'
import { GapNotice } from '../components/ui/GapNotice'
import tableStyles from '../styles/table.module.css'
import styles from './LaunchPage.module.css'

// `configs/experiments/*.yaml` reales del repo (verificado con `ls rio_search/backend/configs/
// experiments/` durante la Fase 5). No hay endpoint en la API de la Fase 4 para *listar* los YAML
// disponibles (`POST /api/jobs` solo valida que el nombre pedido exista dentro de
// `experiments_dir`) -- este selector es una lista estatica documentada, no una llamada real; si
// se agrega un config nuevo hace falta redeployar el frontend o escribir el nombre a mano abajo.
const KNOWN_CONFIGS = [
  { file: 'persistence_baseline_v1.yaml', desc: 'Baseline naive: ultimo valor observado' },
  { file: 'climatology_baseline_v1.yaml', desc: 'Baseline naive: climatologia por dia del año' },
  { file: 'seasonal_naive_baseline_v1.yaml', desc: 'Baseline naive: estacional' },
  { file: 'bilstm_baseline_v1.yaml', desc: 'BiLSTM, multi_output, caudal' },
  { file: 'bilstm_baseline_v1_per_horizon.yaml', desc: 'BiLSTM, per_horizon, caudal' },
]

export function LaunchPage() {
  const [configFile, setConfigFile] = useState(KNOWN_CONFIGS[0].file)
  const [customConfig, setCustomConfig] = useState('')
  const [label, setLabel] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [submitError, setSubmitError] = useState<string | null>(null)
  const [activeJobId, setActiveJobId] = useState<string | undefined>(undefined)
  const logBoxRef = useRef<HTMLPreElement>(null)
  const queryClient = useQueryClient()

  const { data, isLoading } = useQuery({
    queryKey: ['jobs'],
    queryFn: fetchJobs,
    refetchInterval: 3000,
  })

  const { lines, done } = useJobLog(activeJobId)

  useEffect(() => {
    if (logBoxRef.current) logBoxRef.current.scrollTop = logBoxRef.current.scrollHeight
  }, [lines])

  useEffect(() => {
    if (done) queryClient.invalidateQueries({ queryKey: ['jobs'] })
  }, [done, queryClient])

  async function handleSubmit() {
    const config = customConfig.trim() || configFile
    setSubmitting(true)
    setSubmitError(null)
    try {
      const job = await submitJob(config, label.trim() || undefined)
      setActiveJobId(job.job_id)
      queryClient.invalidateQueries({ queryKey: ['jobs'] })
    } catch (e) {
      setSubmitError((e as Error).message)
    } finally {
      setSubmitting(false)
    }
  }

  const jobs = data?.jobs ?? []

  return (
    <div className={styles.page}>
      <h1>Lanzar</h1>
      <p>
        Corre <code>rio-search search run configs/experiments/&lt;archivo&gt;.yaml</code> en cola local
        (un job a la vez, §3.9/Decisión de la Fase 4), con log en vivo por SSE.
      </p>

      <GapNotice>
        El plan (§3.9) pide un "formulario desde un YAML editable": la API de la Fase 4 solo acepta un
        <em> nombre de archivo</em> ya existente en <code>configs/experiments/</code> (
        <code>POST /api/jobs</code>) -- no hay endpoint para listar, leer ni escribir el contenido de un
        YAML. Esta página deja elegir entre los configs reales conocidos hoy (lista estática, abajo) o
        escribir el nombre de uno nuevo a mano; la edición real del contenido queda pendiente de un
        endpoint nuevo (<code>GET/PUT /api/configs/{'{name}'}</code>) fuera del alcance de esta fase.
      </GapNotice>

      <Panel title="Nueva búsqueda">
        <div className={styles.form}>
          <label>
            Config conocido
            <select value={configFile} onChange={(e) => setConfigFile(e.target.value)}>
              {KNOWN_CONFIGS.map((c) => (
                <option key={c.file} value={c.file}>
                  {c.file} — {c.desc}
                </option>
              ))}
            </select>
          </label>
          <label>
            …o nombre de archivo custom (override)
            <input
              placeholder="mi_experimento_v2.yaml"
              value={customConfig}
              onChange={(e) => setCustomConfig(e.target.value)}
            />
          </label>
          <label>
            Label (opcional)
            <input placeholder="descripcion corta" value={label} onChange={(e) => setLabel(e.target.value)} />
          </label>
          <button className={styles.submitBtn} onClick={handleSubmit} disabled={submitting}>
            {submitting ? 'Lanzando…' : 'Lanzar búsqueda'}
          </button>
          {submitError && <p className={styles.error}>{submitError}</p>}
        </div>
      </Panel>

      {activeJobId && (
        <Panel title={`Log en vivo — job ${activeJobId}`}>
          <pre ref={logBoxRef} className={styles.log}>
            {lines.length === 0 ? '(esperando líneas…)' : lines.join('\n')}
          </pre>
          {done && <Badge tone="neutral">stream cerrado</Badge>}
        </Panel>
      )}

      <Panel title="Cola de jobs">
        {isLoading && <p>Cargando…</p>}
        <div className={tableStyles.wrap}>
          <table className={tableStyles.table}>
            <thead>
              <tr>
                <th>job</th>
                <th>config</th>
                <th>estado</th>
                <th>creado</th>
                <th>run</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {jobs.map((j: JobOut) => (
                <tr key={j.job_id}>
                  <td>
                    {j.label} <small className="mono">{j.job_id.slice(0, 8)}</small>
                  </td>
                  <td className="mono">{j.config_path.split(/[\\/]/).pop()}</td>
                  <td>
                    <Badge tone={jobStatusTone(j.status)}>{j.status}</Badge>
                  </td>
                  <td>{formatDateTimeMs(Date.parse(j.created_at))}</td>
                  <td>
                    {j.extra.search_run_id ? (
                      <Link to={`/runs/${j.extra.search_run_id}`}>ver run →</Link>
                    ) : (
                      '—'
                    )}
                  </td>
                  <td>
                    <button onClick={() => setActiveJobId(j.job_id)}>ver log</button>
                  </td>
                </tr>
              ))}
              {jobs.length === 0 && !isLoading && (
                <tr>
                  <td colSpan={6}>Sin jobs todavía.</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
        <p className={styles.note}>
          La cola de jobs vive en memoria del proceso de la API (no sobrevive un reinicio del backend —
          decisión deliberada de la Fase 4: la fuente de verdad es MLflow, <code>GET /api/runs</code>).
        </p>
      </Panel>
    </div>
  )
}
