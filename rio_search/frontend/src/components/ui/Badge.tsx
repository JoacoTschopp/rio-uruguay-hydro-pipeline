import type { ReactNode } from 'react'
import styles from './Badge.module.css'

export type Tone = 'good' | 'warning' | 'serious' | 'critical' | 'neutral'

export function Badge({ tone = 'neutral', children }: { tone?: Tone; children: ReactNode }) {
  return (
    <span className={styles.badge} data-tone={tone}>
      {children}
    </span>
  )
}
