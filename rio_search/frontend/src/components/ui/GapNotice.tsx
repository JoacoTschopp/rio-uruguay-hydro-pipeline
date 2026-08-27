import type { ReactNode } from 'react'
import styles from './GapNotice.module.css'

/**
 * Aviso explicito de "esto no esta disponible todavia" cuando la API de la Fase 4 no expone un
 * dato que el plan (§3.9) pide para esta pagina. Nunca se rellena con datos inventados: se
 * documenta el hueco y se deja el hueco visible en la UI (y en el reporte de cierre de la Fase 5).
 */
export function GapNotice({ children }: { children: ReactNode }) {
  return (
    <div className={styles.notice}>
      <strong>No disponible todavia.</strong> {children}
    </div>
  )
}
