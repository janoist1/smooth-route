import type { Page, Response } from '@playwright/test'

/** Dense data in the dev DB (Budapest, Belváros). */
export const BUDAPEST = { lat: 47.5007, lng: 19.0517 }
/** Middle of Lake Balaton: no roads, so nothing else is drawn there. */
export const BALATON = { lat: 46.86, lng: 17.79 }

export const mapUrl = (at: { lat: number; lng: number }, zoom: number) =>
  `/?lat=${at.lat}&lng=${at.lng}&z=${zoom}`

type GqlBody = { operationName?: string; variables?: Record<string, unknown> }

export const gqlOperation = (response: Response): string | undefined => {
  if (!response.url().endsWith('/graphql')) return undefined
  try {
    return (response.request().postDataJSON() as GqlBody | null)?.operationName
  } catch {
    return undefined
  }
}

/**
 * Wait for a GraphQL response of `operationName` whose data satisfies
 * `accept` (e.g. "has rows") — the map can fire the same query more than once
 * while the viewport settles.
 */
export const waitForGql = <T = unknown>(
  page: Page,
  operationName: string,
  accept: (data: T) => boolean = () => true,
) =>
  page.waitForResponse(async response => {
    if (gqlOperation(response) !== operationName || !response.ok()) return false
    const body = (await response.json()) as { data?: T }
    return body.data != null && accept(body.data)
  })

/** Answer a GraphQL operation with a canned result (other operations pass through). */
export const mockGql = async (page: Page, operationName: string, data: unknown) => {
  await page.route('**/graphql', async route => {
    const body = route.request().postDataJSON() as GqlBody | null
    if (body?.operationName !== operationName) return route.fallback()
    return route.fulfill({ json: { data } })
  })
}

/** Web-Mercator world pixel of a coordinate at an integer zoom (Leaflet's CRS). */
const worldPixel = (lat: number, lng: number, zoom: number) => {
  const size = 256 * 2 ** zoom
  const rad = (lat * Math.PI) / 180
  return {
    x: ((lng + 180) / 360) * size,
    y: ((1 - Math.log(Math.tan(rad) + 1 / Math.cos(rad)) / Math.PI) / 2) * size,
  }
}

/** Current map centre/zoom as the app writes it to the URL after each move. */
export const viewFromUrl = (page: Page) => {
  const params = new URL(page.url()).searchParams
  return {
    lat: Number(params.get('lat')),
    lng: Number(params.get('lng')),
    zoom: Number(params.get('z')),
  }
}

/**
 * Projector from lat/lng to page coordinates for the current map view (one
 * round trip for the map box; the projection itself is local).
 */
export const screenProjector = async (page: Page) => {
  const box = await page.locator('.leaflet-container').boundingBox()
  if (!box) throw new Error('map container not rendered')
  const view = viewFromUrl(page)
  const c = worldPixel(view.lat, view.lng, view.zoom)
  const centre = { x: box.x + box.width / 2, y: box.y + box.height / 2 }
  return {
    box,
    centre,
    toScreen: (lat: number, lng: number) => {
      const p = worldPixel(lat, lng, view.zoom)
      return { x: centre.x + (p.x - c.x), y: centre.y + (p.y - c.y) }
    },
  }
}

/** RGBA of the Leaflet vector canvas (points, grid, route) at a page point; null = no canvas yet. */
export const canvasPixel = (page: Page, x: number, y: number) =>
  page.evaluate(
    ([px, py]) => {
      const canvas = document.querySelector<HTMLCanvasElement>('.leaflet-overlay-pane canvas')
      if (!canvas) return null
      const rect = canvas.getBoundingClientRect()
      const scale = canvas.width / rect.width
      const ctx = canvas.getContext('2d')
      if (!ctx) return null
      const [r, g, b, a] = ctx.getImageData(
        Math.round((px - rect.left) * scale),
        Math.round((py - rect.top) * scale),
        1,
        1,
      ).data
      return { r, g, b, a }
    },
    [x, y] as const,
  )

/** First of `candidates` (page coordinates) not covered by a floating panel, i.e. the map canvas gets the click. */
export const firstOnMapCanvas = (page: Page, candidates: { x: number; y: number }[]) =>
  page.evaluate(points => {
    return (
      points.find(({ x, y }) => {
        const hit = document.elementFromPoint(x, y)
        return hit instanceof HTMLCanvasElement && hit.closest('.leaflet-overlay-pane') !== null
      }) ?? null
    )
  }, candidates)

