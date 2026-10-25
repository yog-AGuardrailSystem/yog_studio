import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

const backend = 'http://localhost:8000'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    // one entry per backend route group, so the browser never hits CORS
    proxy: {
      '/api': { target: backend, rewrite: (p) => p.replace(/^\/api/, '') },
    },
  },
})
