// Route alternatives (Google's alternative routes + their road quality).
// Pure helpers, unit-tested in alternatives.test.ts.
import type { RouteQuality } from './segments/types'

export interface RouteAlternative {
  index: number
  points: [number, number][]
  distanceM: number
  durationS: number
  summary: string
  quality: RouteQuality
  /** Measured share of the route, 0–1. */
  coverage: number
  isFastest: boolean
  isSmoothest: boolean
}

export interface RouteAlternativesResult {
  routes: RouteAlternative[]
  fastestIndex: number | null
  smoothestIndex: number | null
}

/** The route shown first: the smoothest when one qualifies, else the fastest. */
export const defaultRouteIndex = (res: RouteAlternativesResult): number | null => {
  if (res.routes.length === 0) return null
  return res.smoothestIndex ?? res.fastestIndex ?? res.routes[0].index
}

/** "23 perc" / "1 ó 05 perc". */
export const formatDuration = (seconds: number): string => {
  const minutes = Math.max(1, Math.round(seconds / 60))
  if (minutes < 60) return `${minutes} perc`
  return `${Math.floor(minutes / 60)} ó ${String(minutes % 60).padStart(2, '0')} perc`
}

/** "+4 perc" against the fastest route; "" for the fastest itself. */
export const extraDurationLabel = (route: RouteAlternative, fastest: RouteAlternative | undefined): string => {
  if (!fastest || route.index === fastest.index) return ''
  const extra = Math.round((route.durationS - fastest.durationS) / 60)
  return extra > 0 ? `+${extra} perc` : ''
}
