import { test, expect, type Page } from '@playwright/test'
import {
  BALATON,
  BUDAPEST,
  canvasPixel,
  firstOnMapCanvas,
  gqlOperation,
  mapUrl,
  mockGql,
  screenProjector,
  viewFromUrl,
  waitForGql,
} from './helpers'

// Layers by zoom (frontend/src/modules/map/segments/style.ts):
// grid below 13, road segments from 13, plus frame dots from 16.
type GridData = { roadQualityGrid: { cells: unknown[] } | null }
type SegmentsData = { roadSegments: { id: string; path: [number, number][] }[] }
type PointsData = { points: { id: number; latitude: number; longitude: number }[] }

const hasCells = (d: GridData) => (d.roadQualityGrid?.cells.length ?? 0) > 0
const hasSegments = (d: SegmentsData) => d.roadSegments.length > 0
const hasPoints = (d: PointsData) => d.points.length > 0

const zoomIn = async (page: Page, to: number) => {
  await page.locator('.leaflet-control-zoom-in').click()
  await expect(page).toHaveURL(new RegExp(`[?&]z=${to}\\b`))
}

/** Click a page point: phones tap (touch events), desktops click. */
const press = async (page: Page, isMobile: boolean, at: { x: number; y: number }) => {
  if (isMobile) await page.touchscreen.tap(at.x, at.y)
  else await page.mouse.click(at.x, at.y)
}

/** Middle of a polyline's longest edge: a point that lies on the drawn line. */
const pointOnPath = (path: [number, number][]) => {
  let best = { len: -1, lat: path[0][0], lng: path[0][1] }
  for (let i = 1; i < path.length; i++) {
    const [aLat, aLng] = path[i - 1]
    const [bLat, bLng] = path[i]
    const len = Math.hypot(bLat - aLat, (bLng - aLng) * Math.cos((aLat * Math.PI) / 180))
    if (len > best.len) best = { len, lat: (aLat + bLat) / 2, lng: (aLng + bLng) / 2 }
  }
  return best
}

test('map loads with the road-quality grid when zoomed out', async ({ page }) => {
  const grid = waitForGql<GridData>(page, 'GetRoadQualityGrid', hasCells)
  await page.goto(mapUrl(BUDAPEST, 12))

  await expect(page.locator('.leaflet-container')).toBeVisible()
  await expect(page.getByText('Jelmagyarázat')).toBeVisible()
  await grid
  // OpenStreetMap attribution is required wherever road geometry is drawn.
  await expect(page.locator('.leaflet-control-attribution')).toContainText('OpenStreetMap')
})

test('zooming in switches grid → road segments → frame dots', async ({ page }) => {
  const grid = waitForGql<GridData>(page, 'GetRoadQualityGrid', hasCells)
  await page.goto(mapUrl(BUDAPEST, 12))
  await grid

  const segments = waitForGql<SegmentsData>(page, 'GetRoadSegments', hasSegments)
  await zoomIn(page, 13)
  await segments

  await zoomIn(page, 14)
  await zoomIn(page, 15)
  const dots = waitForGql<PointsData>(page, 'GetPoints', hasPoints)
  await zoomIn(page, 16)
  await dots
})

test('clicking a road segment opens its card', async ({ page, isMobile }) => {
  const response = waitForGql<SegmentsData>(page, 'GetRoadSegments', hasSegments)
  // Zoom 15: segments without frame dots on top of them.
  await page.goto(mapUrl(BUDAPEST, 15))
  const { roadSegments } = ((await (await response).json()) as { data: SegmentsData }).data
  await expect(page).toHaveURL(/[?&]z=15\b/)

  const { centre, toScreen } = await screenProjector(page)
  const byDistance = roadSegments
    .map(s => pointOnPath(s.path))
    .map(p => toScreen(p.lat, p.lng))
    .sort((a, b) => Math.hypot(a.x - centre.x, a.y - centre.y) - Math.hypot(b.x - centre.x, b.y - centre.y))
  const target = await firstOnMapCanvas(page, byDistance)
  if (!target) throw new Error(`no uncovered segment on the map at ${JSON.stringify(viewFromUrl(page))}`)

  await press(page, isMobile, target)

  const card = page.getByRole('region', { name: 'Útszakasz részletei' })
  await expect(card).toBeVisible()
  await expect(card.getByTestId('segment-quality')).toContainText('Pontszám')
  await expect(card.getByTestId('segment-pbad')).toContainText('%')
  await expect(card.getByTestId('segment-confidence')).toContainText('Megbízhatóság')
  await expect(card.getByRole('link', { name: /Street View/ })).toHaveAttribute(
    'href',
    /^https:\/\/www\.google\.com\/maps\//,
  )
})

test('clicking a frame dot opens the point card', async ({ page, isMobile }) => {
  const pointsResponse = waitForGql<PointsData>(page, 'GetPoints', hasPoints)
  await page.goto(mapUrl(BUDAPEST, 17))
  const { points } = ((await (await pointsResponse).json()) as { data: PointsData }).data
  await expect(page).toHaveURL(/[?&]z=17\b/)

  // Nearest dot to the middle of the map that no floating panel covers.
  const { centre, toScreen } = await screenProjector(page)
  const byDistance = points
    .map(p => toScreen(p.latitude, p.longitude))
    .sort((a, b) => Math.hypot(a.x - centre.x, a.y - centre.y) - Math.hypot(b.x - centre.x, b.y - centre.y))
  const target = await firstOnMapCanvas(page, byDistance)
  if (!target) throw new Error(`no uncovered point on the map at ${JSON.stringify(viewFromUrl(page))}`)

  const detail = page.waitForResponse(r => gqlOperation(r) === 'GetPointDetail')
  await press(page, isMobile, target)
  await detail

  await expect(page.getByTestId('capture-date')).toContainText('Kép készült:')
  await expect(page.getByRole('link', { name: /Street View/ })).toHaveAttribute(
    'href',
    /^https:\/\/www\.google\.com\/maps\//,
  )
})

test('route planner submits the form, draws the route and summarises it', async ({ page, isMobile }) => {
  // Deterministic and free: no Google Directions call, no sign-in needed.
  await mockGql(page, 'Viewer', { me: null })
  await mockGql(page, 'GetRoute', {
    getRoute: {
      points: [
        { lat: BALATON.lat, lng: BALATON.lng - 0.05, __typename: 'RouteStep' },
        { lat: BALATON.lat, lng: BALATON.lng + 0.05, __typename: 'RouteStep' },
      ],
      __typename: 'RouteData',
    },
  })

  // Zoom 12 (grid level): the route is a plain blue line, not the
  // blue-and-dark "tube" drawn over road segments.
  await page.goto(mapUrl(BALATON, 12))
  await expect(page).toHaveURL(/[?&]z=12\b/)

  // On a phone the planner starts folded into its round button.
  const origin = page.getByPlaceholder('pl. Budapest, Hősök tere')
  if (isMobile && !(await origin.isVisible())) {
    await page.getByTitle('Útvonaltervezés és Elemzés').click()
  }
  await origin.fill('Siófok')
  await page.getByPlaceholder('pl. Szeged, Dóm tér').fill('Balatonfüred')
  const request = page.waitForRequest(r => {
    if (!r.url().endsWith('/graphql')) return false
    return (r.postDataJSON() as { operationName?: string } | null)?.operationName === 'GetRoute'
  })
  const quality = page.waitForResponse(r => gqlOperation(r) === 'GetRouteQuality')
  await page.getByRole('button', { name: /Útvonal Mutatása/ }).click()

  expect((await request).postDataJSON().variables).toEqual({
    origin: 'Siófok',
    destination: 'Balatonfüred',
  })
  await expect(page.getByText('Route not found')).toBeHidden()

  // The mocked route crosses the map centre: the vector canvas turns blue there.
  const { centre } = await screenProjector(page)
  await expect
    .poll(async () => {
      const px = await canvasPixel(page, centre.x, centre.y)
      return px !== null && px.a > 0 && px.b > px.r + 40 && px.b > px.g
    })
    .toBe(true)

  // Route-quality summary from the real backend (~7.6 km across the lake, no road data).
  expect((await quality).ok()).toBe(true)
  const summary = page.getByRole('region', { name: 'Útvonal minősége' })
  await expect(summary.getByTestId('route-total')).toContainText('km')

  // Anonymous visitors only get the preview, not the (auth-only) analysis.
  await expect(page.getByRole('button', { name: /Elemzés Indítása/ })).toBeHidden()
})
