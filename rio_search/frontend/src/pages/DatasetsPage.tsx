import { Fragment, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { fetchDataset, fetchFeatures, type RefreshMode } from '../lib/api'
import { Badge } from '../components/ui/Badge'
import { Panel } from '../components/ui/Panel'
import { GapNotice } from '../components/ui/GapNotice'
import tableStyles from '../styles/table.module.css'
import styles from './DatasetsPage.module.css'

export function DatasetsPage() {
  const [mode, setMode] = useState<RefreshMode>('offline')
  const [expandedGroup, setExpandedGroup] = useState<string | null>(null)
  const [showAllColumns, setShowAllColumns] = useState(false)

  const dataset = useQuery({
    queryKey: ['dataset', mode],
    queryFn: () => fetchDataset(mode),
  })
  const features = useQuery({
    queryKey: ['features'],
    queryFn: fetchFeatures,
  })

  return (
    <div className={styles.page}>
      <h1>Datasets</h1>
      <p>
        Versión del snapshot activo y catálogo de grupos de features. Fuente: <code>GET /api/datasets</code>{' '}
        y <code>GET /api/features</code>.
      </p>

      <Panel
        title="Versión del dataset"
        actions={
          <label className={styles.modeLabel}>
            modo
            <select value={mode} onChange={(e) => setMode(e.target.value as RefreshMode)}>
              <option value="offline">offline (default, no toca Databricks)</option>
              <option value="volume_as_is">volume_as_is</option>
              <option value="ensure_latest">ensure_latest (puede tardar minutos)</option>
            </select>
          </label>
        }
      >
        {dataset.isLoading && <p>Cargando…</p>}
        {dataset.error && <p style={{ color: 'var(--status-critical)' }}>{(dataset.error as Error).message}</p>}
        {dataset.data && (
          <>
            <div className={styles.summaryGrid}>
              <Item label="delta_version" value={String(dataset.data.dataset_version.delta_version)} />
              <Item label="sha256" value={dataset.data.dataset_version.sha256} mono />
              <Item label="filas" value={dataset.data.dataset_version.rows.toLocaleString('es-UY')} />
              <Item
                label="rango de fechas"
                value={`${dataset.data.dataset_version.fecha_min} → ${dataset.data.dataset_version.fecha_max}`}
              />
              <Item label="punto_prediccion" value={dataset.data.dataset_version.punto_prediccion ?? '—'} />
              <Item label="exported_at" value={dataset.data.dataset_version.exported_at ?? '—'} />
              <Item label="modo consultado" value={dataset.data.mode} />
              <Item label="columnas" value={String(dataset.data.dataset_version.columns.length)} />
            </div>
            <p className={styles.cachePath}>
              cache local: <code>{dataset.data.cache_path}</code>
            </p>
            <button className={styles.linkBtn} onClick={() => setShowAllColumns((s) => !s)}>
              {showAllColumns ? 'Ocultar columnas' : `Ver las ${dataset.data.dataset_version.columns.length} columnas`}
            </button>
            {showAllColumns && (
              <div className={styles.columnGrid}>
                {dataset.data.dataset_version.columns.map((c) => (
                  <code key={c} className={styles.columnChip}>
                    {c}
                  </code>
                ))}
              </div>
            )}
          </>
        )}
      </Panel>

      <GapNotice>
        El plan (§3.9) pide "cobertura por columna y por año" en esta página. <code>GET /api/datasets</code>{' '}
        solo devuelve la versión del snapshot (delta, sha, filas, rango, columnas) -- la cobertura real ya
        existe en el backend (<code>DescribeDataset</code>, Fase 1, usada por{' '}
        <code>rio-search datasets describe</code>) pero no está conectada a un endpoint HTTP todavía (así lo
        documenta la Decisión de cierre de la Fase 4). No se agregó ese endpoint acá para no tocar el
        backend más allá del montaje de estáticos; queda para un endpoint dedicado.
      </GapNotice>

      <Panel title="Grupos de features">
        {features.isLoading && <p>Cargando…</p>}
        {features.error && <p style={{ color: 'var(--status-critical)' }}>{(features.error as Error).message}</p>}
        {features.data && (
          <div className={tableStyles.wrap}>
            <table className={tableStyles.table}>
              <thead>
                <tr>
                  <th></th>
                  <th>grupo</th>
                  <th>default</th>
                  <th className={tableStyles.num}>columnas</th>
                  <th className={tableStyles.wrapCell}>descripción</th>
                </tr>
              </thead>
              <tbody>
                {features.data.groups.map((g) => (
                  <Fragment key={g.name}>
                    <tr>
                      <td>
                        <button className={styles.expandBtn} onClick={() => setExpandedGroup(expandedGroup === g.name ? null : g.name)}>
                          {expandedGroup === g.name ? '▾' : '▸'}
                        </button>
                      </td>
                      <td className="mono">{g.name}</td>
                      <td>
                        <Badge tone={g.default_on ? 'good' : 'neutral'}>{g.default_on ? 'on' : 'off'}</Badge>
                      </td>
                      <td className={tableStyles.num}>{g.columns.length}</td>
                      <td className={tableStyles.wrapCell}>{g.description}</td>
                    </tr>
                    {expandedGroup === g.name && (
                      <tr>
                        <td></td>
                        <td colSpan={4}>
                          <div className={styles.columnGrid}>
                            {g.columns.length === 0 && <span>(vacío)</span>}
                            {g.columns.map((c) => (
                              <code key={c} className={styles.columnChip}>
                                {c}
                              </code>
                            ))}
                          </div>
                        </td>
                      </tr>
                    )}
                  </Fragment>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Panel>

      <GapNotice>
        "Transforms disponibles" (§3.9) no tiene endpoint propio: viven como código en{' '}
        <code>infrastructure/preprocess/transforms/</code> (<code>log1p</code>, <code>doy_cyclic</code>,{' '}
        <code>clip</code>, <code>ratio</code>, <code>diff</code>, <code>rolling</code>) y se declaran por
        YAML de experimento (§4.1 del plan), no por un catálogo consultable en runtime.
      </GapNotice>
    </div>
  )
}

function Item({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className={styles.item}>
      <span className={styles.itemLabel}>{label}</span>
      <span className={mono ? 'mono' : undefined}>{value}</span>
    </div>
  )
}
