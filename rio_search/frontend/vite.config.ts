import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
// En desarrollo, Vite proxea /api al backend FastAPI (rio_search/backend, ver §3.9 del plan).
// En produccion, FastAPI sirve el build estatico (rio-search api serve), sin proxy.
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
})
