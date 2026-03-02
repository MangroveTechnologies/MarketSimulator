import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5200,
    proxy: {
      '/api': 'http://localhost:5100',
    },
  },
  build: {
    outDir: '../experiment_ui_dist',
    emptyOutDir: true,
  },
})
