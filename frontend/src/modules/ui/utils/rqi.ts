// RQI presentation helpers (marker colour, quality label, which model's score
// to show). The scale itself (levels, labels, colours, direction, bad-road
// boundary) is defined once in shared/rqi_scale.json and read via ./rqiScale;
// nothing here hard-codes a level number or a threshold.
import { RQI_UNKNOWN, nearestRqiLevel, rqiLevel, towardWorseRqiLevel } from './rqiScale'
import type { RqiLevelKey } from './rqiScale'

export type RqiDisplaySource = 'yolo' | 'dino' | 'both'

/** The two model scores a point can carry. */
export interface RqiScores {
  rqi_score?: number | null // YOLO damage-derived score
  dino_rqi_score?: number | null // frozen DINOv2 + trained head
}

/** Resolved score to display, plus which model produced it. */
export interface ResolvedRqi {
  score?: number
  model: 'yolo' | 'dino'
  label: string
}

/**
 * Marker / badge colour for a score: the colour of the level reached when
 * rounding toward the worse level (so 2.01 already shows Közepes yellow).
 * Kiváló and Jó share the map green by design.
 */
export const getRQIColor = (score?: number | null): string => {
  if (score === undefined || score === null) return RQI_UNKNOWN.color
  return rqiLevel(towardWorseRqiLevel(score))?.color ?? RQI_UNKNOWN.color
}

// Legacy English wording kept verbatim: map/segments/labels.ts translates these
// strings to Hungarian. New code should use rqiScoreLabelHu (./rqiScale).
const LEGACY_LABEL_EN: Record<RqiLevelKey, string> = {
  excellent: 'Excellent',
  good: 'Good',
  fair: 'Fair',
  poor: 'Poor',
  very_poor: 'Critical',
}

/** English quality label of the nearest level (halves toward the better one). */
export const getRQILabel = (score?: number | null): string => {
  if (score === undefined || score === null) return RQI_UNKNOWN.label_en
  const level = rqiLevel(nearestRqiLevel(score))
  return level ? LEGACY_LABEL_EN[level.key] : RQI_UNKNOWN.label_en
}

/**
 * Decide which model's score to display for a point given the configured source.
 * 'dino' and 'both' prefer the DINO score and fall back to YOLO when it is
 * missing; 'yolo' always uses the YOLO score.
 */
export const resolveRqi = (point: RqiScores, source: RqiDisplaySource): ResolvedRqi => {
  const dino = point.dino_rqi_score
  const yolo = point.rqi_score
  const hasDino = dino !== undefined && dino !== null

  if ((source === 'dino' || source === 'both') && hasDino) {
    return { score: dino ?? undefined, model: 'dino', label: 'DINO' }
  }
  if (source === 'dino') {
    return { score: yolo ?? undefined, model: 'yolo', label: 'YOLO (Fallback)' }
  }
  return { score: yolo ?? undefined, model: 'yolo', label: 'YOLO' }
}
