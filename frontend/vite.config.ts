import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import checker from 'vite-plugin-checker'
import path from 'path'

// Dev-server proxy target. Default: the local backend from `make dev`.
// Override to run a second stack side by side (e.g. a git worktree):
//   BACKEND_URL=http://localhost:8003 npm run dev -- --port 5176
const BACKEND_URL = process.env.BACKEND_URL ?? 'http://localhost:8000'

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [
    react(),
    checker({
      typescript: true,
      eslint: {
        lintCommand: 'eslint "./src/**/*.{ts,tsx}"',
        useFlatConfig: true, // Needed for ESLint 9+ which Vite uses now
      },
    }),
  ],
  server: {
    proxy: {
      '/api': {
        target: BACKEND_URL,
        changeOrigin: true,
      },
      '/graphql': {
        target: BACKEND_URL,
        changeOrigin: true,
      },
      '/images': {
        target: BACKEND_URL,
        changeOrigin: true,
      },
      '/previews': {
        target: BACKEND_URL,
        changeOrigin: true,
      },
    },
  },
  optimizeDeps: {
    exclude: ['@graphql-typed-document-node/core'],
  },
  resolve: {
    alias: {
      '@graphql-typed-document-node/core': path.resolve('./src/modules/graphql/shim.ts'),
      'modules': path.resolve(import.meta.dirname, './src/modules'),
    },
  },
})
