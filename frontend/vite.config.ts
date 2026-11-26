import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import checker from 'vite-plugin-checker'
import path from 'path'

// Backend the dev server proxies to (default: `make backend` on :8000).
// Override e.g. for the E2E suite or a second backend: API_PROXY_TARGET=http://localhost:8002
const apiTarget = 
  process.env.API_PROXY_TARGET ?? process.env.BACKEND_URL ?? 'http://localhost:8000'
const proxied = { target: apiTarget, changeOrigin: true }

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
      '/api': proxied,
      '/graphql': proxied,
      '/images': proxied,
      '/previews': proxied,
    },
  },
  build: {
    rolldownOptions: {
      output: {
        // Big, rarely changing vendors in their own long-cacheable chunks, so
        // an app deploy does not make returning phone users re-download them.
        // (Admin pages and Clerk are separate lazy chunks: components/Routes.tsx,
        // modules/auth/AuthProvider.tsx.)
        codeSplitting: {
          groups: [
            { name: 'vendor-react', test: /node_modules[\\/](react|react-dom|scheduler)[\\/]/, priority: 30 },
            { name: 'vendor-leaflet', test: /node_modules[\\/](leaflet|react-leaflet|@react-leaflet)[\\/]/, priority: 20 },
            {
              name: 'vendor-apollo',
              test: /node_modules[\\/](@apollo|graphql|rxjs|optimism|@wry|tslib|ts-invariant)[\\/]/,
              priority: 10,
            },
          ],
        },
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
