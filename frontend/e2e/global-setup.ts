// Fail fast with a clear message when the backend the dev server proxies to
// is not running, instead of every test timing out on an empty map.
export default async function globalSetup() {
  const backend = process.env.API_PROXY_TARGET ?? 'http://localhost:8000'
  try {
    const res = await fetch(`${backend}/health`)
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
  } catch (err) {
    throw new Error(
      `E2E: backend not reachable at ${backend}/health (${String(err)}). ` +
        'Start it with `make backend` (or `make dev`), or set API_PROXY_TARGET.',
    )
  }
}
