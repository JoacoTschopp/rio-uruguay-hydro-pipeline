import { useEffect, useState, type ReactNode } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  NOTE_SECTIONS,
  createDocument,
  documentFileUrl,
  exportBibtex,
  fetchDocumentDetail,
  fetchDocuments,
  updateDocumentNote,
  updateDocumentTags,
  type DocumentType,
  type LinkKind,
  type LinkOut,
} from '../lib/api'
import { Badge } from '../components/ui/Badge'
import { Panel } from '../components/ui/Panel'
import { GapNotice } from '../components/ui/GapNotice'
import tableStyles from '../styles/table.module.css'
import styles from './ResearchPage.module.css'

const DOCUMENT_TYPES: { value: DocumentType; label: string }[] = [
  { value: 'paper', label: 'paper' },
  { value: 'tesis', label: 'tesis' },
  { value: 'informe', label: 'informe' },
  { value: 'plantilla', label: 'plantilla' },
]

export function ResearchPage() {
  const queryClient = useQueryClient()
  const [selectedSlug, setSelectedSlug] = useState<string | null>(null)

  const documents = useQuery({ queryKey: ['research-documents'], queryFn: fetchDocuments })

  useEffect(() => {
    // Selecciona el primer documento apenas hay alguno cargado, si todavía no hay seleccion.
    if (!selectedSlug && documents.data && documents.data.documents.length > 0) {
      setSelectedSlug(documents.data.documents[0].slug)
    }
  }, [documents.data, selectedSlug])

  function invalidate() {
    queryClient.invalidateQueries({ queryKey: ['research-documents'] })
    if (selectedSlug) queryClient.invalidateQueries({ queryKey: ['research-document', selectedSlug] })
  }

  return (
    <div className={styles.page}>
      <h1>Research</h1>
      <p>
        Biblioteca de documentos de la tesis (§3.10 del plan): catálogo + notas por sección + BibTeX, sin LLM
        (Decisión #3). Persistencia en <code>rio_search/research/catalog/*.yaml</code> +{' '}
        <code>rio_search/research/notes/*.md</code>; los PDF quedan fuera de git.
      </p>

      <AddDocumentPanel onCreated={(slug) => {
        invalidate()
        setSelectedSlug(slug)
      }} />

      <Panel title="Documentos">
        {documents.isLoading && <p>Cargando…</p>}
        {documents.error && (
          <p style={{ color: 'var(--status-critical)' }}>{(documents.error as Error).message}</p>
        )}
        {documents.data && documents.data.documents.length === 0 && (
          <GapNotice>Sin documentos todavía. Cargá el primero con el formulario de arriba.</GapNotice>
        )}
        {documents.data && documents.data.documents.length > 0 && (
          <div className={tableStyles.wrap}>
            <table className={tableStyles.table}>
              <thead>
                <tr>
                  <th>slug</th>
                  <th>título</th>
                  <th>autores</th>
                  <th className={tableStyles.num}>año</th>
                  <th>tipo</th>
                  <th>tags</th>
                  <th>archivo</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {documents.data.documents.map((d) => (
                  <tr key={d.slug} className={d.slug === selectedSlug ? styles.selectedRow : undefined}>
                    <td className="mono">{d.slug}</td>
                    <td>{d.title}</td>
                    <td>{d.authors.join('; ')}</td>
                    <td className={tableStyles.num}>{d.year}</td>
                    <td>
                      <Badge tone="neutral">{d.type}</Badge>
                    </td>
                    <td>
                      {d.tags.map((t) => (
                        <span key={t} className={styles.tagChip}>
                          {t}
                        </span>
                      ))}
                    </td>
                    <td>
                      {d.file ? (
                        <a href={documentFileUrl(d.slug)} target="_blank" rel="noreferrer">
                          ver
                        </a>
                      ) : (
                        '—'
                      )}
                    </td>
                    <td>
                      <button onClick={() => setSelectedSlug(d.slug)}>editar</button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Panel>

      {selectedSlug && <DocumentDetailPanel slug={selectedSlug} onChanged={invalidate} />}

      <ExportBibtexPanel />
    </div>
  )
}

function AddDocumentPanel({ onCreated }: { onCreated: (slug: string) => void }) {
  const [title, setTitle] = useState('')
  const [authors, setAuthors] = useState('')
  const [year, setYear] = useState('')
  const [type, setType] = useState<DocumentType>('paper')
  const [venue, setVenue] = useState('')
  const [doiUrl, setDoiUrl] = useState('')
  const [tags, setTags] = useState('')
  const [slug, setSlug] = useState('')
  const [file, setFile] = useState<File | null>(null)
  const [error, setError] = useState<string | null>(null)

  const mutation = useMutation({
    mutationFn: () =>
      createDocument({
        title,
        authors,
        year: Number(year),
        type,
        venue: venue || undefined,
        doi_url: doiUrl || undefined,
        tags,
        slug: slug || undefined,
        file,
      }),
    onSuccess: (detail) => {
      setTitle('')
      setAuthors('')
      setYear('')
      setVenue('')
      setDoiUrl('')
      setTags('')
      setSlug('')
      setFile(null)
      setError(null)
      onCreated(detail.document.slug)
    },
    onError: (e) => setError((e as Error).message),
  })

  return (
    <Panel title="Agregar documento">
      <form
        className={styles.form}
        onSubmit={(e) => {
          e.preventDefault()
          mutation.mutate()
        }}
      >
        <label>
          Título
          <input required value={title} onChange={(e) => setTitle(e.target.value)} />
        </label>
        <label>
          Autores (separados por ';')
          <input
            required
            placeholder="Hochreiter, S.; Schmidhuber, J."
            value={authors}
            onChange={(e) => setAuthors(e.target.value)}
          />
        </label>
        <label>
          Año
          <input required type="number" value={year} onChange={(e) => setYear(e.target.value)} />
        </label>
        <label>
          Tipo
          <select value={type} onChange={(e) => setType(e.target.value as DocumentType)}>
            {DOCUMENT_TYPES.map((t) => (
              <option key={t.value} value={t.value}>
                {t.label}
              </option>
            ))}
          </select>
        </label>
        <label>
          Venue (revista / conferencia / institución)
          <input value={venue} onChange={(e) => setVenue(e.target.value)} />
        </label>
        <label>
          DOI / URL
          <input value={doiUrl} onChange={(e) => setDoiUrl(e.target.value)} />
        </label>
        <label>
          Tags (separados por ',')
          <input placeholder="lstm,hidrologia" value={tags} onChange={(e) => setTags(e.target.value)} />
        </label>
        <label>
          Slug (opcional; default derivado de título + año)
          <input placeholder="hochreiter-1997-lstm" value={slug} onChange={(e) => setSlug(e.target.value)} />
        </label>
        <label>
          Archivo (PDF, opcional)
          <input type="file" accept=".pdf,.txt,.md" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
        </label>
        <button className={styles.submitBtn} type="submit" disabled={mutation.isPending}>
          {mutation.isPending ? 'Agregando…' : 'Agregar documento'}
        </button>
        {error && <p className={styles.error}>{error}</p>}
      </form>
    </Panel>
  )
}

function DocumentDetailPanel({ slug, onChanged }: { slug: string; onChanged: () => void }) {
  const detail = useQuery({ queryKey: ['research-document', slug], queryFn: () => fetchDocumentDetail(slug) })
  const [tagsInput, setTagsInput] = useState('')
  const [sections, setSections] = useState<Record<string, string>>({})
  const [links, setLinks] = useState<LinkOut[]>([])
  const [linkKind, setLinkKind] = useState<LinkKind>('decision')
  const [linkRef, setLinkRef] = useState('')
  const [noteSavedAt, setNoteSavedAt] = useState<string | null>(null)
  const [tagsSavedAt, setTagsSavedAt] = useState<string | null>(null)
  const [noteError, setNoteError] = useState<string | null>(null)
  const [tagsError, setTagsError] = useState<string | null>(null)

  useEffect(() => {
    if (detail.data) {
      setTagsInput(detail.data.document.tags.join(','))
      setSections(detail.data.note.sections)
      setLinks(detail.data.note.links)
      setNoteSavedAt(null)
      setTagsSavedAt(null)
    }
  }, [detail.data])

  const tagsMutation = useMutation({
    mutationFn: () => updateDocumentTags(slug, tagsInput),
    onSuccess: () => {
      setTagsSavedAt(new Date().toLocaleTimeString('es-UY'))
      setTagsError(null)
      onChanged()
    },
    onError: (e) => setTagsError((e as Error).message),
  })

  const noteMutation = useMutation({
    mutationFn: () => updateDocumentNote(slug, sections, links),
    onSuccess: () => {
      setNoteSavedAt(new Date().toLocaleTimeString('es-UY'))
      setNoteError(null)
      onChanged()
    },
    onError: (e) => setNoteError((e as Error).message),
  })

  if (detail.isLoading) return <Panel title={`Documento: ${slug}`}><p>Cargando…</p></Panel>
  if (detail.error) {
    return (
      <Panel title={`Documento: ${slug}`}>
        <p style={{ color: 'var(--status-critical)' }}>{(detail.error as Error).message}</p>
      </Panel>
    )
  }
  if (!detail.data) return null

  const { document } = detail.data

  return (
    <Panel title={`Editar: ${document.title}`}>
      <div className={styles.summaryGrid}>
        <Item label="slug" value={document.slug} />
        <Item label="autores" value={document.authors.join('; ')} />
        <Item label="año" value={String(document.year)} />
        <Item label="tipo" value={document.type} />
        <Item label="venue" value={document.venue ?? '—'} />
        <Item label="doi/url" value={document.doi_url ?? '—'} />
        <Item label="agregado" value={document.added_at} />
        <Item
          label="archivo"
          value={document.file ? <a href={documentFileUrl(slug)} target="_blank" rel="noreferrer">ver / descargar</a> : '—'}
        />
      </div>

      <div className={styles.subsection}>
        <h3>Tags</h3>
        <div className={styles.inlineForm}>
          <input
            value={tagsInput}
            onChange={(e) => setTagsInput(e.target.value)}
            placeholder="lstm,hidrologia,forecasting"
          />
          <button onClick={() => tagsMutation.mutate()} disabled={tagsMutation.isPending}>
            {tagsMutation.isPending ? 'Guardando…' : 'Guardar tags'}
          </button>
          {tagsSavedAt && <span className={styles.savedAt}>guardado {tagsSavedAt}</span>}
        </div>
        {tagsError && <p className={styles.error}>{tagsError}</p>}
      </div>

      <div className={styles.subsection}>
        <h3>Notas por sección</h3>
        {NOTE_SECTIONS.map((s) => (
          <label key={s.key} className={styles.noteSectionLabel}>
            {s.label}
            <textarea
              rows={3}
              value={sections[s.key] ?? ''}
              onChange={(e) => setSections((prev) => ({ ...prev, [s.key]: e.target.value }))}
            />
          </label>
        ))}

        <h4>Enlaces (Decisión / run)</h4>
        <ul className={styles.linkList}>
          {links.map((l, i) => (
            <li key={`${l.kind}-${l.ref}-${i}`}>
              <Badge tone="neutral">{l.kind === 'decision' ? `Decisión ${l.ref}` : `run ${l.ref}`}</Badge>
              <button
                type="button"
                className={styles.removeLinkBtn}
                onClick={() => setLinks((prev) => prev.filter((_, idx) => idx !== i))}
              >
                quitar
              </button>
            </li>
          ))}
          {links.length === 0 && <li className={styles.noLinks}>Sin enlaces todavía.</li>}
        </ul>
        <div className={styles.inlineForm}>
          <select value={linkKind} onChange={(e) => setLinkKind(e.target.value as LinkKind)}>
            <option value="decision">Decisión</option>
            <option value="run">Run (MLflow)</option>
          </select>
          <input
            placeholder={linkKind === 'decision' ? '041' : 'run_id'}
            value={linkRef}
            onChange={(e) => setLinkRef(e.target.value)}
          />
          <button
            type="button"
            onClick={() => {
              if (!linkRef.trim()) return
              setLinks((prev) => [...prev, { kind: linkKind, ref: linkRef.trim() }])
              setLinkRef('')
            }}
          >
            agregar enlace
          </button>
        </div>

        <div className={styles.inlineForm}>
          <button onClick={() => noteMutation.mutate()} disabled={noteMutation.isPending}>
            {noteMutation.isPending ? 'Guardando…' : 'Guardar nota'}
          </button>
          {noteSavedAt && <span className={styles.savedAt}>guardado {noteSavedAt}</span>}
        </div>
        {noteError && <p className={styles.error}>{noteError}</p>}
      </div>
    </Panel>
  )
}

function ExportBibtexPanel() {
  const [result, setResult] = useState<{ output_path: string; entry_count: number; keys: string[] } | null>(
    null,
  )
  const [error, setError] = useState<string | null>(null)
  const mutation = useMutation({
    mutationFn: exportBibtex,
    onSuccess: (r) => {
      setResult(r)
      setError(null)
    },
    onError: (e) => setError((e as Error).message),
  })

  return (
    <Panel title="Exportar BibTeX">
      <p>
        Escribe <code>rio_search/thesis/common/references.bib</code> — una entrada por documento del
        catálogo, clave = slug. La tesis cita con <code>\cite{'{slug}'}</code>.
      </p>
      <button onClick={() => mutation.mutate()} disabled={mutation.isPending}>
        {mutation.isPending ? 'Exportando…' : 'Exportar BibTeX'}
      </button>
      {error && <p className={styles.error}>{error}</p>}
      {result && (
        <div className={styles.summaryGrid}>
          <Item label="archivo" value={result.output_path} />
          <Item label="entradas" value={String(result.entry_count)} />
          <Item label="claves" value={result.keys.join(', ') || '—'} />
        </div>
      )}
    </Panel>
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
