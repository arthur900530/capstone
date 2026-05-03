import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  // @novnc/novnc uses top-level await for WebCodecs H.264 capability
  // detection, so we need a target that supports it. esnext lets esbuild
  // pass it through unchanged.
  build: {
    target: 'esnext',
  },
  optimizeDeps: {
    esbuildOptions: { target: 'esnext' },
  },
  server: {
    proxy: {
      // The noVNC iframe sits same-origin behind /api/browser/proxy/, and
      // its WebSocket lives at /api/browser/proxy/websockify. Vite's
      // pattern-matching is "first match wins"; this rule is listed before
      // the catch-all `/api` so the WS upgrade is forwarded with `ws:true`.
      '/api/browser/proxy/websockify': {
        target: 'ws://localhost:8000',
        ws: true,
        changeOrigin: true,
      },
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      '/ws': {
        target: 'ws://localhost:8000',
        ws: true,
      },
    },
  },
})
