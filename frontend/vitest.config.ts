import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'
import path from 'path'

// Standalone test config (no vite-plugin-checker) so `vitest` runs fast and
// independently of the dev-server type/lint checker.
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@graphql-typed-document-node/core': path.resolve(import.meta.dirname, './src/modules/graphql/shim.ts'),
      modules: path.resolve(import.meta.dirname, './src/modules'),
    },
  },
  // Tests may read ../shared (the canonical RQI scale) to check the bundled copy.
  server: {
    fs: { allow: [import.meta.dirname, path.resolve(import.meta.dirname, '../shared')] },
  },
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
    include: ['src/**/*.{test,spec}.{ts,tsx}'],
  },
})
