import { useQuery } from '@tanstack/react-query'
import { fetchHealth } from '../lib/api'
import { Panel } from '../components/ui/Panel'

// Diagnostico de bajo nivel heredado de la Fase 0 (criterio de cierre: "npm run dev muestra la
// respuesta de GET /api/health"). Las paginas de contenido (Busquedas, Run, Comparar, Lanzar,
// Datasets, Fase 5) viven en sus propios archivos; esta queda como chequeo de cableado
// backend<->frontend, enlazada desde el badge de estado del backend en la barra superior.
export function HealthPage() {
  const { data, error, isLoading } = useQuery({
    queryKey: ['health'],
    queryFn: fetchHealth,
    retry: 1,
  })

  return (
    <Panel title="Estado del backend — GET /api/health">
      {isLoading && <p>Consultando backend...</p>}
      {error && (
        <pre style={{ color: 'var(--status-critical)' }}>
          {error instanceof Error ? error.message : String(error)}
          {'\n\n'}
          (Levantá el backend con: cd rio_search/backend && .venv/Scripts/python -m
          rio_search.interfaces.cli.main api serve)
        </pre>
      )}
      {data && <pre>{JSON.stringify(data, null, 2)}</pre>}
    </Panel>
  )
}
