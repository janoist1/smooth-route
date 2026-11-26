import { test, expect } from '@playwright/test'
import { gqlOperation } from './helpers'

// Quick-rate page (/training/quick) is admin-only. It needs a backend that
// treats the visitor as admin: locally AUTH_MODE=disabled, e.g.
//   API_PROXY_TARGET=http://localhost:8003 E2E_PORT=5181 npm run test:e2e
// Read-only smoke: it never rates, skips or undoes (those write to the DB).
test('quick-rate page loads a frame and switches to re-check mode', async ({ page, request }) => {
  const me = await request.post('/graphql', { data: { query: '{ me { role } }' } })
  const role = ((await me.json()) as { data?: { me?: { role?: string } | null } }).data?.me?.role
  test.skip(role !== 'admin', 'needs an admin backend (AUTH_MODE=disabled), see the comment above')

  const queue = page.waitForResponse(r => gqlOperation(r) === 'LabelQueue')
  await page.goto('/training/quick')
  expect((await queue).ok()).toBe(true)

  await expect(page.getByRole('img', { name: /Street View kép #\d+/ })).toBeVisible()
  for (const label of ['Kiváló', 'Jó', 'Közepes', 'Rossz']) {
    await expect(page.getByRole('button', { name: label, exact: true })).toBeVisible()
  }

  // Scale help opens and closes.
  await page.getByRole('button', { name: 'Skála és példák' }).click()
  const rubric = page.getByRole('dialog', { name: 'Értékelési skála' })
  await expect(rubric).toBeVisible()
  await rubric.getByRole('button', { name: 'Bezárás' }).click()
  await expect(rubric).toBeHidden()

  // Re-check mode asks the backend for the RECHECK queue.
  const recheck = page.waitForRequest(r => {
    if (!r.url().endsWith('/graphql')) return false
    const body = r.postDataJSON() as { operationName?: string; variables?: { strategy?: string } } | null
    return body?.operationName === 'LabelQueue' && body.variables?.strategy === 'RECHECK'
  })
  await page.getByRole('button', { name: 'Újraellenőrzés' }).click()
  await recheck
  await expect(page.getByRole('alert')).toBeHidden()
})
