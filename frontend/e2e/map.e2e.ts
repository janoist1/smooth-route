import { test, expect } from '@playwright/test'
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

type GridData = { roadQualityGrid: { cells: unknown[] } | null }
type PointsData = { points: { id: number; latitude: number; longitude: number }[] }

const hasCells = (d: GridData) => (d.roadQualityGrid?.cells.length ?? 0) > 0
const hasPoints = (d: PointsData) => d.points.length > 0

// Only shown while individual points are on the map (zoomed in).
const staleToggle = 'Régi képek halványítása'

test('map loads with the road-quality grid when zoomed out', async ({ page }) => {
  const grid = waitForGql<GridData>(page, 'GetRoadQualityGrid', hasCells)
  await page.goto(mapUrl(BUDAPEST, 13))

  await expect(page.locator('.leaflet-container')).toBeVisible()
  await expect(page.getByText('Útvonaltervező')).toBeVisible()
  await expect(page.getByText('Smooth Route')).toBeVisible()
  await grid
  await expect(page.getByText(staleToggle)).toBeHidden()
})

test('zooming in switches from the grid to individual points', async ({ page }) => {
  const grid = waitForGql<GridData>(page, 'GetRoadQualityGrid', hasCells)
  await page.goto(mapUrl(BUDAPEST, 13))
  await grid

  const points = waitForGql<PointsData>(page, 'GetPoints', hasPoints)
  await page.locator('.leaflet-control-zoom-in').click()

  await points
  await expect(page).toHaveURL(/[?&]z=14\b/)
  await expect(page.getByText(staleToggle)).toBeVisible()
})

test('clicking a point opens its detail card', async ({ page, isMobile }) => {
  const pointsResponse = waitForGql<PointsData>(page, 'GetPoints', hasPoints)
  await page.goto(mapUrl(BUDAPEST, 17))
  const { points } = ((await (await pointsResponse).json()) as { data: PointsData }).data
  await expect(page).toHaveURL(/[?&]z=17\b/)

  // Nearest point to the middle of the map that no floating panel covers.
  const { centre, toScreen } = await screenProjector(page)
  const byDistance = points
    .map(p => toScreen(p.latitude, p.longitude))
    .sort((a, b) => Math.hypot(a.x - centre.x, a.y - centre.y) - Math.hypot(b.x - centre.x, b.y - centre.y))
  const target = await firstOnMapCanvas(page, byDistance)
  if (!target) throw new Error(`no uncovered point on the map at ${JSON.stringify(viewFromUrl(page))}`)

  const detail = page.waitForResponse(r => gqlOperation(r) === 'GetPointDetail')
  // Phones tap (touch events), desktops click.
  if (isMobile) await page.touchscreen.tap(target.x, target.y)
  else await page.mouse.click(target.x, target.y)
  await detail

  await expect(page.getByTestId('capture-date')).toContainText('Kép készült:')
  await expect(page.getByRole('link', { name: /Street View/ })).toHaveAttribute(
    'href',
    /^https:\/\/www\.google\.com\/maps\//,
  )
})

test('route planner submits the form and draws the route', async ({ page }) => {
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

  await page.goto(mapUrl(BALATON, 13))
  await expect(page).toHaveURL(/[?&]z=13\b/)

  await page.getByPlaceholder('pl. Budapest, Hősök tere').fill('Siófok')
  await page.getByPlaceholder('pl. Szeged, Dóm tér').fill('Balatonfüred')
  const request = page.waitForRequest(r => {
    if (!r.url().endsWith('/graphql')) return false
    return (r.postDataJSON() as { operationName?: string } | null)?.operationName === 'GetRoute'
  })
  await page.getByRole('button', { name: /Útvonal Mutatása/ }).click()

  expect((await request).postDataJSON().variables).toEqual({
    origin: 'Siófok',
    destination: 'Balatonfüred',
  })
  await expect(page.getByRole('button', { name: /Útvonal Mutatása/ })).toBeEnabled()
  await expect(page.getByText('Route not found')).toBeHidden()

  // The mocked route crosses the map centre: the vector canvas turns blue there.
  const { centre } = await screenProjector(page)
  await expect
    .poll(async () => {
      const px = await canvasPixel(page, centre.x, centre.y)
      return px !== null && px.a > 0 && px.b > px.r + 40 && px.b > px.g
    })
    .toBe(true)

  // Anonymous visitors only get the preview, not the (auth-only) analysis.
  await expect(page.getByRole('button', { name: /Elemzés Indítása/ })).toBeHidden()
})
