// Client-side policy for the road-segment layer: which layer shows at which
// zoom, and how a segment is drawn. Pure functions so they can be unit-tested
// (no Leaflet import); the returned style is a plain Leaflet PathOptions subset.
import { getRQIColor } from '../../ui'
import { GRID_MAX_ZOOM } from '../aggregation'
import { isStaleCapture } from '../captureDate'
import type { RoadSegment } from './types'

/** From this zoom up, roads are drawn as coloured segments. Must match the
 *  backend: `roadSegments` returns [] below it. */
export const SEGMENT_MIN_ZOOM = 13

/** From this zoom up, the individual frame dots are shown on top of the
 *  segments (below it they only appear around a selected segment). */
export const FRAME_DOT_MIN_ZOOM = 16

export interface MapLayers {
  /** Average-RQI grid (zoomed-out overview). */
  grid: boolean
  /** Coloured road segments. */
  segments: boolean
  /** Individual clickable frame dots for the whole viewport. */
  frames: boolean
}

/**
 * Which layers the map shows (and fetches) at a zoom level.
 *
 *   zoom < 13   grid
 *   13–15       segments
 *   >= 16       segments + frame dots
 *
 * `segmentsSupported = false` (backend without the segment API) restores the
 * legacy split: grid below 14, dots from 14.
 */
export const layersForZoom = (zoom: number, segmentsSupported = true): MapLayers => {
  if (!segmentsSupported) {
    const grid = zoom < GRID_MAX_ZOOM
    return { grid, segments: false, frames: !grid }
  }
  const segments = zoom >= SEGMENT_MIN_ZOOM
  return { grid: !segments, segments, frames: zoom >= FRAME_DOT_MIN_ZOOM }
}

/** Line weight (px): thin when a whole district is visible, bold street-level. */
export const segmentWeight = (zoom: number): number => {
  if (zoom <= 13) return 3
  if (zoom >= 17) return 7
  return 3 + (Math.floor(zoom) - 13) // 14 → 4, 15 → 5, 16 → 6
}

const MIN_OPACITY = 0.35

/** 0.35 (no confidence) … 1.0 (full confidence): unsure roads fade out. */
export const segmentOpacity = (confidence?: number | null): number => {
  const c = Number.isFinite(confidence) ? Math.max(0, Math.min(1, confidence as number)) : 0
  return MIN_OPACITY + (1 - MIN_OPACITY) * c
}

export const isLowConfidence = (segment: Pick<RoadSegment, 'confidenceLevel'>): boolean =>
  segment.confidenceLevel === 'low'

/** A segment is "old" when even its NEWEST image is past the stale threshold. */
export const isStaleSegment = (
  segment: Pick<RoadSegment, 'captureDateMax'>,
  now: Date = new Date(),
): boolean => isStaleCapture(segment.captureDateMax, now)

export interface SegmentStyle {
  color: string
  weight: number
  opacity: number
  /** Present only for low-confidence segments (dashed line). */
  dashArray?: string
  lineCap: 'round' | 'butt'
}

export interface SegmentStyleOptions {
  /** Pointer is over the segment. */
  hovered?: boolean
  /** "Dim old images" filter is on and this segment is stale. */
  dimmed?: boolean
}

/**
 * Colour = quality class, opacity = confidence, dashed = low confidence.
 * An unrated segment (rqi null) is grey.
 */
export const segmentStyle = (
  segment: Pick<RoadSegment, 'rqi' | 'confidence' | 'confidenceLevel'>,
  zoom: number,
  { hovered = false, dimmed = false }: SegmentStyleOptions = {},
): SegmentStyle => {
  const weight = segmentWeight(zoom) + (hovered ? 2 : 0)
  const low = isLowConfidence(segment)
  let opacity = segmentOpacity(segment.confidence)
  if (dimmed) opacity *= 0.35
  if (hovered) opacity = Math.min(1, opacity + 0.25)

  return {
    color: getRQIColor(segment.rqi),
    weight,
    opacity: Math.round(opacity * 1000) / 1000,
    // Dash length follows the weight so the pattern reads the same at any zoom.
    // Butt caps keep the gaps open (round caps would close them on thick lines).
    ...(low ? { dashArray: `${weight * 2} ${Math.round(weight * 1.5)}` } : {}),
    lineCap: low ? 'butt' : 'round',
  }
}

/**
 * Dark outline drawn under a segment so the quality colours keep their
 * contrast on light base maps (invisible on the dark one). It follows the
 * segment's own opacity and dash pattern.
 */
export const segmentCasingStyle = (style: SegmentStyle): SegmentStyle => ({
  color: '#0b1220',
  weight: style.weight + 2,
  opacity: Math.round(style.opacity * 0.6 * 1000) / 1000,
  ...(style.dashArray ? { dashArray: style.dashArray } : {}),
  lineCap: style.lineCap,
})

/** White outline drawn under the selected segment. */
export const selectionHaloStyle = (zoom: number) => ({
  color: '#ffffff',
  weight: segmentWeight(zoom) + 7,
  opacity: 0.9,
  lineCap: 'round' as const,
})
