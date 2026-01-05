import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import checker from 'vite-plugin-checker'
import path from 'path'

// https://vitejs.dev/config/
// Trigger reload
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
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      '/graphql': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      '/images': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        rewrite: path => path.replace(/^\/images/, '/api/v1/images'),
      },
    },
  },
  optimizeDeps: {
    exclude: ['@graphql-typed-document-node/core'],
  },
  resolve: {
    alias: {
      '@graphql-typed-document-node/core': path.resolve('./src/modules/graphql/shim.ts'),
      'modules': path.resolve(__dirname, './src/modules'),
    },
  },
})
