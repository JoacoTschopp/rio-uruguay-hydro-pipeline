// Cliente HTTP minimo para /api/*. Fase 0 solo necesita /api/health; el resto de
// endpoints (§3.9 del plan) se agregan junto con sus paginas en fases posteriores.
export interface HealthResponse {
  status: string
  service: string
  version: string
}

export async function fetchHealth(): Promise<HealthResponse> {
  const res = await fetch('/api/health')
  if (!res.ok) {
    throw new Error(`GET /api/health -> ${res.status} ${res.statusText}`)
  }
  return (await res.json()) as HealthResponse
}
