import { defineConfig, devices } from '@playwright/test'

/**
 * Local E2E smoke suite (`npm run test:e2e`) — not part of CI yet.
 *
 * Needs a running backend with map data (the dev Postgres): `make backend`
 * (or `make dev`) on :8000, or point API_PROXY_TARGET at another one. The
 * suite starts its own Vite dev server on E2E_PORT (default 5180) proxying to
 * that backend, or reuses an already running app via E2E_BASE_URL.
 *
 * Browser: the locally installed Google Chrome (no browser download). To use
 * Playwright's bundled Chromium instead: `npx playwright install chromium` and
 * E2E_CHANNEL=bundled.
 */
const port = Number(process.env.E2E_PORT ?? 5180)
const baseURL = process.env.E2E_BASE_URL ?? `http://localhost:${port}`
const channel = process.env.E2E_CHANNEL ?? 'chrome'
const browser = channel === 'bundled' ? {} : { channel }

export default defineConfig({
  testDir: './e2e',
  testMatch: '**/*.e2e.ts',
  globalSetup: './e2e/global-setup.ts',
  fullyParallel: true,
  // Small suite against one shared dev backend: keep the load down, and allow
  // for a cold Vite (on-demand compile) and a busy machine.
  workers: Number(process.env.E2E_WORKERS ?? 2),
  forbidOnly: !!process.env.CI,
  retries: 0,
  timeout: 60_000,
  expect: { timeout: 20_000 },
  reporter: [['list'], ['html', { open: 'never' }]],
  use: {
    baseURL,
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
  projects: [
    { name: 'desktop', use: { ...devices['Desktop Chrome'], ...browser } },
    { name: 'mobile', use: { ...devices['Pixel 7'], ...browser } },
  ],
  webServer: process.env.E2E_BASE_URL
    ? undefined
    : {
        command: `npx vite --port ${port} --strictPort`,
        url: baseURL,
        reuseExistingServer: true,
        timeout: 60_000,
      },
})
