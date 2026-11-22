import path from 'node:path'
import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vitest/config'

// Em desenvolvimento, /api vai para o `isoterma servir` local: sem CORS e sem URL fixa no código.
const API = process.env.ISOTERMA_API ?? 'http://127.0.0.1:8000'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: { '@': path.resolve(import.meta.dirname, './src') },
  },
  server: {
    proxy: { '/api': { target: API, changeOrigin: true } },
  },
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/testes/setup.ts'],
    css: false,
  },
})
