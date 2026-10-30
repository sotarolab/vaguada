import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// Served by the FastAPI app at the root. In development /api is proxied to the service.
export default defineConfig({
  plugins: [react()],
  base: '/',
  server: {
    proxy: {
      '/api': { target: process.env.VITE_API_TARGET ?? 'http://localhost:8070', changeOrigin: true },
      '/healthz': { target: process.env.VITE_API_TARGET ?? 'http://localhost:8070', changeOrigin: true },
    },
  },
  build: { outDir: 'dist', emptyOutDir: true },
})
