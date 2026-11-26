import { test, expect } from '@playwright/test'
import AxeBuilder from '@axe-core/playwright'
import { BUDAPEST, mapUrl, waitForGql } from './helpers'

type SegmentsData = { roadSegments: unknown[] }

// axe-core over the public map page (WCAG 2.1 A/AA rules). Leaflet's own tile
// and canvas panes are left out: they are an image of the map, not controls.
test('map page has no serious accessibility violations', async ({ page }) => {
  const segments = waitForGql<SegmentsData>(page, 'GetRoadSegments', d => d.roadSegments.length > 0)
  await page.goto(mapUrl(BUDAPEST, 15))
  await segments

  const results = await new AxeBuilder({ page })
    .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'])
    .exclude('.leaflet-tile-pane')
    .exclude('.leaflet-overlay-pane')
    .analyze()
  const serious = results.violations.filter(v => v.impact === 'serious' || v.impact === 'critical')
  const summary = serious.map(v => `${v.id} (${v.impact}): ${v.nodes.length}× ${v.nodes[0]?.target.join(' ')}`)
  expect(summary, summary.join('\n')).toEqual([])
})
