// Hungarian wording + number formatting for the road-segment UI. Pure, so the
// exact texts the owner sees are pinned by unit tests.
import { getRQILabel } from '../../ui'
import { formatCaptureDate, isStaleCapture, parseCaptureDate } from '../captureDate'
import type { RoadSegment } from './types'

// The quality bands come from getRQILabel (single source of truth for the
// thresholds); only the wording is translated here.
const QUALITY_HU: Record<string, string> = {
  Excellent: 'Kiváló',
  Good: 'Jó',
  Fair: 'Közepes',
  Poor: 'Rossz',
  Critical: 'Nagyon rossz',
  Unknown: 'Nincs adat',
}

/** Hungarian quality label for an RQI class or score (1 = Kiváló … 4 = Rossz). */
export const rqiLabelHu = (score?: number | null): string => {
  const label = getRQILabel(score)
  return QUALITY_HU[label] ?? label
}

/** Quality classes the app uses (5 is never produced), best first. */
export const RQI_CLASSES = [1, 2, 3, 4] as const

const CONFIDENCE_HU: Record<string, string> = {
  high: 'magas',
  medium: 'közepes',
  low: 'alacsony',
}

/** "magas" / "közepes" / "alacsony"; "ismeretlen" for an unexpected level. */
export const confidenceLabelHu = (level?: string | null): string =>
  (level && CONFIDENCE_HU[level]) || 'ismeretlen'

/**
 * One plain sentence on WHY the confidence is what it is. The API only gives
 * the level and the frame count, so the wording names both possible causes
 * (few frames / disagreeing frames) instead of guessing one.
 */
export const confidenceExplanation = (level: string | null | undefined, nImages: number): string => {
  const n = Math.max(0, Math.round(nImages))
  if (n === 0) return 'Nincs hozzá képkocka – a becslés nem ellenőrizhető.'
  const basis = `${n} képkocka alapján`
  switch (level) {
    case 'high':
      return `${basis}; a képek egybehangzóan ugyanazt mutatják.`
    case 'medium':
      return `${basis}; a képek nem teljesen egyeznek, vagy kevés a kép.`
    case 'low':
      return `${basis}; kevés a kép, vagy a becslések ellentmondanak – kezeld fenntartással.`
    default:
      return `${basis}.`
  }
}

// OSM `highway` tag → everyday Hungarian road type.
const HIGHWAY_HU: Record<string, string> = {
  motorway: 'autópálya',
  motorway_link: 'autópálya-csomópont',
  trunk: 'autóút',
  trunk_link: 'autóút-csomópont',
  primary: 'főút',
  primary_link: 'főút-csomópont',
  secondary: 'összekötő út',
  secondary_link: 'összekötő út',
  tertiary: 'gyűjtőút',
  tertiary_link: 'gyűjtőút',
  unclassified: 'egyéb közút',
  residential: 'lakóutca',
  living_street: 'lakó-pihenő övezet',
  service: 'szervizút',
  track: 'földút',
  road: 'közút',
  pedestrian: 'sétálóutca',
  cycleway: 'kerékpárút',
}

/** Hungarian road type for an OSM highway tag; null when unknown/missing. */
export const highwayLabelHu = (highway?: string | null): string | null => {
  if (!highway) return null
  return HIGHWAY_HU[highway] ?? highway.replace(/_/g, ' ')
}

const capitalize = (s: string) => s.charAt(0).toUpperCase() + s.slice(1)

/** Card / list title: the street name, else the road type, else a generic name. */
export const segmentTitle = (segment: Pick<RoadSegment, 'roadName' | 'highway'>): string => {
  const name = segment.roadName?.trim()
  if (name) return name
  const type = highwayLabelHu(segment.highway)
  return type ? `${capitalize(type)} (névtelen)` : 'Névtelen útszakasz'
}

/** Hungarian decimal comma: 2.25 → "2,3" (digits = 1). */
export const formatDecimal = (value: number, digits = 1): string =>
  value.toFixed(digits).replace('.', ',')

/** "85 m" below a kilometre, "1,2 km" above, "12 km" from 10 km. */
export const formatLength = (metres?: number | null): string => {
  if (metres == null || !Number.isFinite(metres) || metres < 0) return '–'
  if (metres < 1000) return `${Math.round(metres)} m`
  const km = metres / 1000
  return `${km < 10 ? formatDecimal(km, 1) : Math.round(km)} km`
}

/** Always kilometres with one decimal ("0,4 km", "62,4 km") — for route totals. */
export const formatKm = (metres?: number | null): string => {
  if (metres == null || !Number.isFinite(metres) || metres < 0) return '–'
  return `${formatDecimal(metres / 1000, 1)} km`
}

/** 0.127 → "13%" (clamped to 0–100). */
export const formatPercent = (ratio?: number | null): string => {
  if (ratio == null || !Number.isFinite(ratio)) return '–'
  return `${Math.round(Math.max(0, Math.min(1, ratio)) * 100)}%`
}

/** "2,3" — the continuous score on the 1–4 scale; "–" when missing. */
export const formatScore = (score?: number | null): string =>
  score == null || !Number.isFinite(score) ? '–' : formatDecimal(score, 1)

/** "2019-06 – 2023-08", a single month when both ends match, "ismeretlen" when unknown. */
export const formatCaptureRange = (min?: string | null, max?: string | null): string => {
  const lo = parseCaptureDate(min) ? formatCaptureDate(min) : null
  const hi = parseCaptureDate(max) ? formatCaptureDate(max) : null
  if (lo && hi) return lo === hi ? lo : `${lo} – ${hi}`
  return lo ?? hi ?? 'ismeretlen'
}

/**
 * How outdated a segment's imagery is, using the point card's stale rule:
 *   'all'  – even the newest image is older than the threshold
 *   'some' – only the oldest images are
 *   'none' – everything is recent (or the dates are unknown)
 */
export type CaptureStaleness = 'none' | 'some' | 'all'

export const captureStaleness = (
  min?: string | null,
  max?: string | null,
  now: Date = new Date(),
): CaptureStaleness => {
  const newest = parseCaptureDate(max) ? max : min
  const oldest = parseCaptureDate(min) ? min : max
  if (isStaleCapture(newest, now)) return 'all'
  if (isStaleCapture(oldest, now)) return 'some'
  return 'none'
}
