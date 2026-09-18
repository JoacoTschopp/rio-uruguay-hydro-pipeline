import { useQuery } from '@tanstack/react-query'
import { NavLink, Outlet } from 'react-router-dom'
import { fetchHealth } from '../lib/api'
import { Badge } from './ui/Badge'
import styles from './Layout.module.css'

const NAV_ITEMS = [
  { to: '/', label: 'Búsquedas', end: true },
  { to: '/compare', label: 'Comparar' },
  { to: '/launch', label: 'Lanzar' },
  { to: '/datasets', label: 'Datasets' },
  { to: '/forecast', label: 'Pronóstico de hoy' },
  { to: '/research', label: 'Research' },
  { to: '/funcion-ganancia', label: 'Función de ganancia' },
]

export function Layout() {
  const { data, isError } = useQuery({
    queryKey: ['health'],
    queryFn: fetchHealth,
    retry: 1,
    refetchInterval: 30_000,
  })

  return (
    <div className={styles.shell}>
      <header className={styles.topbar}>
        <div className={styles.brand}>
          <NavLink to="/" className={styles.brandLink}>
            Rio_Search
          </NavLink>
          <span className={styles.tagline}>caudal · ana_74100000</span>
        </div>
        <nav className={styles.nav}>
          {NAV_ITEMS.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.end}
              className={({ isActive }) => (isActive ? `${styles.link} ${styles.linkActive}` : styles.link)}
            >
              {item.label}
            </NavLink>
          ))}
        </nav>
        <NavLink to="/health" className={styles.health} title="Estado del backend (GET /api/health)">
          {isError ? (
            <Badge tone="critical">backend caído</Badge>
          ) : data ? (
            <Badge tone="good">backend ok · v{data.version}</Badge>
          ) : (
            <Badge tone="neutral">consultando…</Badge>
          )}
        </NavLink>
      </header>
      <main className={styles.main}>
        <Outlet />
      </main>
    </div>
  )
}
