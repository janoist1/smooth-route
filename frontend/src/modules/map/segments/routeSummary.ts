// Route quality summary maths (pure). Turns the `routeQuality` payload into
// the numbers the summary card draws: coverage, the stacked-bar shares and the
// length-weighted average.
import { getRQIColor } from '../../ui'
import { RQI_CLASSES, rqiLabelHu } from './labels'
import type { RouteQuality } from './types'

/** Below this covered share the average is flagged as "based on little data". */
export const LOW_COVERAGE_RATIO = 0.3

export interface RouteClassShare {
  /** Quality class 1–4. */
  rqi: number
  label: string
  color: string
  lengthM: number
  /** Share of the WHOLE route (0–1), so the bar also shows what is unmeasured. */
  share: number
}

export interface RouteSummary {
  totalLengthM: number
  coveredLengthM: number
  /** Covered share of the route, 0–1. */
  coverage: number
  /** False when nothing on the route is measured (or the route is empty). */
  hasData: boolean
  /** True when some, but under LOW_COVERAGE_RATIO, of the route is measured. */
  lowCoverage: boolean
  /** One entry per class 1..4 (zero-length classes included). */
  classes: RouteClassShare[]
  /** Share of the route without data (0–1) — the grey end of the bar. */
  unknownShare: number
  /** Length-weighted mean on the 1–4 scale; null without data. */
  meanScore: number | null
  /** Hungarian label of the mean ("Jó"); "Nincs adat" without data. */
  meanLabel: string
  /** Colour of the class the mean falls into (always agrees with meanLabel). */
  meanColor: string
}

/**
 * Colour for a CONTINUOUS score, by the class its label names. getRQIColor's
 * own bands are cut at whole numbers (2.4 would be yellow) while the label
 * bands are cut at the halves (2.4 is "Jó") — going through the class keeps a
 * badge's colour and text in agreement.
 */
export const rqiClassColor = (score?: number | null): string => {
  if (score == null || !Number.isFinite(score)) return getRQIColor(null)
  return getRQIColor(Math.max(1, Math.ceil(score - 0.5)))
}

const nonNegative = (value: unknown): number =>
  typeof value === 'number' && Number.isFinite(value) && value > 0 ? value : 0

/** Length-weighted mean class from the per-class metres; null when all are 0. */
export const weightedMeanRqi = (lengthByRqi: number[]): number | null => {
  let length = 0
  let weighted = 0
  RQI_CLASSES.forEach((rqi, i) => {
    const metres = nonNegative(lengthByRqi[i])
    length += metres
    weighted += metres * rqi
  })
  return length > 0 ? weighted / length : null
}

export const summarizeRouteQuality = (quality: RouteQuality): RouteSummary => {
  const totalLengthM = nonNegative(quality.totalLengthM)
  const byClass = RQI_CLASSES.map((_, i) => nonNegative(quality.lengthByRqi?.[i]))
  const classified = byClass.reduce((sum, metres) => sum + metres, 0)
  // Covered length can never exceed the route; tolerate a payload where it is
  // missing but the per-class lengths are there.
  const coveredLengthM = Math.min(
    totalLengthM,
    Math.max(nonNegative(quality.coveredLengthM), classified),
  )

  const coverage = totalLengthM > 0 ? coveredLengthM / totalLengthM : 0
  const hasData = coverage > 0

  // Scale down if rounding made the classes add up to more than the route.
  const scale = classified > totalLengthM && classified > 0 ? totalLengthM / classified : 1
  const classes: RouteClassShare[] = RQI_CLASSES.map((rqi, i) => ({
    rqi,
    label: rqiLabelHu(rqi),
    color: getRQIColor(rqi),
    lengthM: byClass[i],
    share: totalLengthM > 0 ? (byClass[i] * scale) / totalLengthM : 0,
  }))
  const classShare = classes.reduce((sum, c) => sum + c.share, 0)

  // Prefer the backend's mean (continuous scores); fall back to the classes.
  const backendMean =
    typeof quality.meanScore === 'number' && Number.isFinite(quality.meanScore)
      ? quality.meanScore
      : null
  const meanScore = hasData ? (backendMean ?? weightedMeanRqi(byClass)) : null

  return {
    totalLengthM,
    coveredLengthM,
    coverage,
    hasData,
    lowCoverage: hasData && coverage < LOW_COVERAGE_RATIO,
    classes,
    unknownShare: Math.max(0, 1 - classShare),
    meanScore,
    meanLabel: rqiLabelHu(meanScore),
    meanColor: rqiClassColor(meanScore),
  }
}
