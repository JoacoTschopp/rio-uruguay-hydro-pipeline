import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
// En desarrollo, Vite proxea /api al backend FastAPI (rio_search/backend, ver §3.9 del plan).
// En produccion, FastAPI sirve el build estatico (rio-search api serve), sin proxy.
// Puerto configurable via VITE_API_PORT (default 8000: el 8000 real puede estar ocupado
// por otro proceso de la maquina, como paso hoy -- usar 8010 en ese caso).
const apiPort = process.env.VITE_API_PORT || '8000'

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': {
        target: `http://127.0.0.1:${apiPort}`,
        changeOrigin: true,
      },
    },
  },
})
