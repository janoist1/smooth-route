// Route alternatives from the selected provider + their road quality.
// Pure helpers, unit-tested in alternatives.test.ts.
import type { RouteQuality } from './segments/types'
import { betterThan } from '../ui/utils/rqiScale'

export interface RouteAlternative {
  provider?: string
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

/** Re-rank stored paths after quality changes, using the API's default policy
 * (docs/API_SURFACE.md, Routes; backend rank_routes). Impact is a cost;
 * canonical mean scores use the scale helper when impact is unavailable. */
export const rankRouteAlternatives = (
  routes: RouteAlternative[],
  maxExtraDuration = 0.2,
  minCoverage = 0.5,
): RouteAlternative[] => {
  if (routes.length === 0) return []
  const refreshed = routes.map(route => ({
    ...route,
    coverage:
      route.quality.totalLengthM > 0
        ? route.quality.coveredLengthM / route.quality.totalLengthM
        : 0,
  }))
  const fastest = refreshed.reduce((best, route) =>
    route.durationS < best.durationS ? route : best,
  )
  const useImpact = refreshed.every(
    route => route.quality.meanScore === null || route.quality.impactScore != null,
  )
  let smoothest: RouteAlternative | undefined
  for (const route of refreshed) {
    const { meanScore, impactScore } = route.quality
    if (
      meanScore === null ||
      route.coverage < minCoverage ||
      route.durationS > fastest.durationS * (1 + maxExtraDuration) + 1e-9
    )
      continue
    if (smoothest) {
      const bestMean = smoothest.quality.meanScore!
      const bestImpact = smoothest.quality.impactScore!
      const better = useImpact ? impactScore! < bestImpact : betterThan(meanScore, bestMean)
      const tie = useImpact ? impactScore === bestImpact : meanScore === bestMean
      if (!better && !(tie && route.durationS < smoothest.durationS)) continue
    }
    smoothest = route
  }
  return refreshed.map(route => ({
    ...route,
    isFastest: route.index === fastest.index,
    isSmoothest: route.index === smoothest?.index,
  }))
}

/** "23 perc" / "1 ó 05 perc". */
export const formatDuration = (seconds: number): string => {
  const minutes = Math.max(1, Math.round(seconds / 60))
  if (minutes < 60) return `${minutes} perc`
  return `${Math.floor(minutes / 60)} ó ${String(minutes % 60).padStart(2, '0')} perc`
}

/** "+4 perc" against the fastest route; "" for the fastest itself. */
export const extraDurationLabel = (
  route: RouteAlternative,
  fastest: RouteAlternative | undefined,
): string => {
  if (!fastest || route.index === fastest.index) return ''
  const extra = Math.round((route.durationS - fastest.durationS) / 60)
  return extra > 0 ? `+${extra} perc` : ''
}

/**
 * User-facing message for a failed route plan. routeAlternatives needs a
 * signed-in user on the full API (anonymous only on the public read-only
 * deploy), and that GraphQL error used to surface as a generic
 * "Hiba a szerver kommunikációban (No Data)".
 */
export const routePlanErrorMessage = (error: unknown): string => {
  const errors = (error as { errors?: { extensions?: { code?: unknown } }[] } | null)?.errors
  if (Array.isArray(errors) && errors.some(e => e?.extensions?.code === 'UNAUTHENTICATED')) {
    return 'Az útvonaltervezéshez jelentkezz be.'
  }
  return 'Az útvonaltervezés nem sikerült, próbáld újra később.'
}
