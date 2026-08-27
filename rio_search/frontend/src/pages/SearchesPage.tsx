import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Link, useNavigate } from 'react-router-dom'
import { fetchSearches, type RunOut, type SearchOut } from '../lib/api'
import { formatDateTimeMs, formatDurationMs, formatNumber, formatSeconds, statusTone } from '../lib/format'
import { Badge } from '../components/ui/Badge'
import { Panel } from '../components/ui/Panel'
import tableStyles from '../styles/table.module.css'
import styles from './SearchesPage.module.css'

type SortKey = 'recent' | 'kge' | 'time' | 'name'

const KNOWN_FAMILY_HINTS = ['baselines', 'bilstm', 'smoke']

function keyMetric(run: RunOut): number | undefined {
  return run.metrics['test/kge/mean'] ?? run.metrics['val/kge/mean']
}

function totalTimeSeconds(run: RunOut): number | undefined {
  return (
    run.metrics['time/search_total_s'] ??
    run.metrics['time/trial_total_s'] ??
    run.metrics['time/train_total_s'] ??
    (run.start_time_ms != null && run.end_time_ms != null ? (run.end_time_ms - run.start_time_ms) / 1000 : undefined)
  )
}

export function SearchesPage() {
  const [familyInput, setFamilyInput] = useState('')
  const [sortKey, setSortKey] = useState<SortKey>('recent')
  const [expanded, setExpanded] = useState<Set<string>>(new Set())
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const navigate = useNavigate()

  const families = familyInput
    .split(',')
    .map((f) => f.trim())
    .filter(Boolean)

  const { data, isLoading, error } = useQuery({
    queryKey: ['searches', families.join(',')],
    queryFn: () => fetchSearches(families.length > 0 ? families : undefined),
  })

  const searches = useMemo(() => {
    const list = data?.searches ?? []
    const sorted = [...list]
    sorted.sort((a, b) => {
      if (sortKey === 'recent') return (b.search.start_time_ms ?? 0) - (a.search.start_time_ms ?? 0)
      if (sortKey === 'name') return a.search.run_name.localeCompare(b.search.run_name)
      if (sortKey === 'kge') return (keyMetric(b.search) ?? bestTrialMetric(b)) - (keyMetric(a.search) ?? bestTrialMetric(a))
      if (sortKey === 'time') return (totalTimeSeconds(b.search) ?? 0) - (totalTimeSeconds(a.search) ?? 0)
      return 0
    })
    return sorted
  }, [data, sortKey])

  function bestTrialMetric(s: SearchOut): number {
    const vals = s.trials.map((t) => keyMetric(t)).filter((v): v is number => v !== undefined)
    return vals.length > 0 ? Math.max(...vals) : -Infinity
  }

  function toggleExpanded(id: string) {
    setExpanded((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  function toggleSelected(id: string) {
    setSelected((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  function goCompare() {
    navigate(`/compare?ids=${Array.from(selected).join(',')}`)
  }

  return (
    <div className={styles.page}>
      <div className={styles.introRow}>
        <div>
          <h1>Búsquedas</h1>
          <p>
            Runs padre (búsquedas) de MLflow y sus trials, con métricas y tiempos reales. Fuente:{' '}
            <code>GET /api/searches</code>.
          </p>
        </div>
      </div>

      <Panel
        title="Filtros"
        actions={
          <>
            <label className={styles.filterLabel}>
              Familias (coma-separadas)
              <input
                className={styles.filterInput}
                placeholder="baselines,bilstm"
                value={familyInput}
                onChange={(e) => setFamilyInput(e.target.value)}
                list="family-hints"
              />
              <datalist id="family-hints">
                {KNOWN_FAMILY_HINTS.map((f) => (
                  <option key={f} value={f} />
                ))}
              </datalist>
            </label>
            <label className={styles.filterLabel}>
              Orden
              <select className={styles.filterInput} value={sortKey} onChange={(e) => setSortKey(e.target.value as SortKey)}>
                <option value="recent">Más reciente</option>
                <option value="kge">Mejor test/kge/mean</option>
                <option value="time">Más tiempo total</option>
                <option value="name">Nombre</option>
              </select>
            </label>
          </>
        }
      >
        {isLoading && <p>Cargando búsquedas…</p>}
        {error && <p style={{ color: 'var(--status-critical)' }}>{(error as Error).message}</p>}
        {!isLoading && !error && searches.length === 0 && <p>No hay búsquedas para este filtro.</p>}
      </Panel>

      {searches.map((s) => (
        <Panel
          key={s.search.run_id}
          title={
            <div className={styles.searchTitle}>
              <button className={styles.expandBtn} onClick={() => toggleExpanded(s.search.run_id)} aria-label="expandir">
                {expanded.has(s.search.run_id) ? '▾' : '▸'}
              </button>
              <Link to={`/runs/${s.search.run_id}`}>{s.search.run_name}</Link>
              <Badge tone={statusTone(s.search.status)}>{s.search.status}</Badge>
            </div>
          }
          actions={
            <div className={styles.searchMeta}>
              <span>{s.search.tags['rio_search.model'] ?? '—'}</span>
              <span>·</span>
              <span>{s.trials.length} trial(s)</span>
              <span>·</span>
              <span>{formatSeconds(totalTimeSeconds(s.search))}</span>
              <span>·</span>
              <span>{formatDateTimeMs(s.search.start_time_ms)}</span>
            </div>
          }
        >
          <div className={styles.searchSummary}>
            <SummaryItem label="target" value={s.search.tags['rio_search.target']} />
            <SummaryItem label="horizon_strategy" value={s.search.tags['rio_search.horizon_strategy']} />
            <SummaryItem label="split_policy" value={s.search.tags['rio_search.split_policy']} />
            <SummaryItem label="train_start" value={s.search.tags['rio_search.train_start']} />
            <SummaryItem label="dataset_delta_version" value={s.search.tags['rio_search.dataset_delta_version']} />
            <SummaryItem label="device" value={s.search.tags['rio_search.device_name'] ?? s.search.tags['rio_search.device']} />
          </div>

          {expanded.has(s.search.run_id) && (
            <div className={tableStyles.wrap}>
              <table className={tableStyles.table}>
                <thead>
                  <tr>
                    <th></th>
                    <th>trial</th>
                    <th>estado</th>
                    <th className={tableStyles.num}>test/kge/mean</th>
                    <th className={tableStyles.num}>test/rmse/mean</th>
                    <th className={tableStyles.num}>tiempo</th>
                    <th>inicio</th>
                  </tr>
                </thead>
                <tbody>
                  {s.trials.map((t) => (
                    <tr key={t.run_id}>
                      <td>
                        <input type="checkbox" checked={selected.has(t.run_id)} onChange={() => toggleSelected(t.run_id)} />
                      </td>
                      <td>
                        <Link to={`/runs/${t.run_id}`}>{t.run_name}</Link>
                      </td>
                      <td>
                        <Badge tone={statusTone(t.status)}>{t.status}</Badge>
                      </td>
                      <td className={tableStyles.num}>{formatNumber(t.metrics['test/kge/mean'], 3)}</td>
                      <td className={tableStyles.num}>{formatNumber(t.metrics['test/rmse/mean'], 1)}</td>
                      <td className={tableStyles.num}>{formatSeconds(totalTimeSeconds(t))}</td>
                      <td>{formatDurationMs(t.start_time_ms, t.end_time_ms)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Panel>
      ))}

      {selected.size > 0 && (
        <div className={styles.compareBar}>
          <span>{selected.size} run(s) seleccionados</span>
          <button onClick={() => setSelected(new Set())}>Limpiar</button>
          <button className={styles.primaryBtn} onClick={goCompare}>
            Comparar →
          </button>
        </div>
      )}
    </div>
  )
}

function SummaryItem({ label, value }: { label: string; value: string | undefined }) {
  return (
    <div className={styles.summaryItem}>
      <span className={styles.summaryLabel}>{label}</span>
      <span className={styles.summaryValue}>{value ?? '—'}</span>
    </div>
  )
}
