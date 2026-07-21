import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

const domainLearningProxy = {
  '/embed/domainlearning-api': {
    target: 'http://127.0.0.1:18880',
    changeOrigin: true,
    rewrite: (path: string) => path.replace(/^\/embed\/domainlearning-api/, ''),
  },
  '/embed/domainlearning': {
    target: 'http://127.0.0.1:8866',
    changeOrigin: true,
    rewrite: (path: string) => path.replace(/^\/embed\/domainlearning/, '') || '/',
  },
}

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173,
    proxy: {
      '/api': 'http://127.0.0.1:8080',
      ...domainLearningProxy,
    },
  },
  preview: {
    port: 5173,
    proxy: {
      '/api': 'http://127.0.0.1:8080',
      ...domainLearningProxy,
    },
  },
})
