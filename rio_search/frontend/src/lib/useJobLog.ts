import { useEffect, useState } from 'react'

// El subproceso de `rio-search search run`/`predict run` imprime con color (MLflow usa ANSI para
// 🏃/🧪, Decision 044) -- se limpia acá para que el <pre> del log muestre texto legible en vez de
// codigos de escape crudos. Extraido de LaunchPage.tsx para reusarlo tal cual en ForecastPage.tsx
// (boton "Predecir hoy", post-Fase 9): ambas paginas siguen el mismo job por SSE.
// eslint-disable-next-line no-control-regex
const ANSI_RE = new RegExp(String.fromCharCode(27) + String.fromCharCode(91) + '[0-9;]*m', 'g')
function stripAnsi(line: string): string {
  return line.replace(ANSI_RE, '')
}

export function useJobLog(jobId: string | undefined) {
  const [lines, setLines] = useState<string[]>([])
  const [done, setDone] = useState(false)
  useEffect(() => {
    setLines([])
    setDone(false)
    if (!jobId) return
    const source = new EventSource(`/api/jobs/${jobId}/log`)
    source.onmessage = (ev) => setLines((prev) => [...prev, stripAnsi(ev.data)])
    source.addEventListener('done', () => {
      setDone(true)
      source.close()
    })
    source.onerror = () => {
      setDone(true)
      source.close()
    }
    return () => source.close()
  }, [jobId])
  return { lines, done }
}
