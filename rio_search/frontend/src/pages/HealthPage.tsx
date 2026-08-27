import { useQuery } from '@tanstack/react-query'
import { fetchHealth } from '../lib/api'

// Criterio de cierre de la Fase 0 (docs/rio_search_plan.md): "npm run dev" debe mostrar
// la respuesta de GET /api/health. Las paginas reales (Busquedas, Run, Comparar, ...)
// llegan en las Fases 4-7; esta es solo la comprobacion de cableado backend <-> frontend.
export function HealthPage() {
  const { data, error, isLoading } = useQuery({
    queryKey: ['health'],
    queryFn: fetchHealth,
    retry: 1,
  })

  return (
    <main style={{ fontFamily: 'system-ui, sans-serif', padding: '2rem' }}>
      <h1>Rio_Search</h1>
      <h2>GET /api/health</h2>
      {isLoading && <p>Consultando backend...</p>}
      {error && (
        <pre style={{ color: 'crimson' }}>
          {error instanceof Error ? error.message : String(error)}
          {'\n\n'}
          (Levanta el backend con: cd rio_search/backend && uv run rio-search api serve)
        </pre>
      )}
      {data && <pre>{JSON.stringify(data, null, 2)}</pre>}
    </main>
  )
}
