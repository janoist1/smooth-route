// Road-segment + route-quality domain types. These mirror the GraphQL contract
// (camelCase, as the API returns them) so no mapping layer is needed:
//
//   roadSegments(bbox: [Float!]!, zoom: Int!): [RoadSegment!]!
//   routeQuality(path: [[Float!]!]!): RouteQuality!
import type { RoadPoint } from '../types'

/** [lat, lng] — the order Leaflet and planRoute use. */
export type LatLng = [number, number]

export type ConfidenceLevel = 'high' | 'medium' | 'low'

export interface RoadSegment {
  id: string
  /** Polyline of the segment, [[lat, lng], ...]. */
  path: LatLng[]
  /** Quality class 1–4 (1 = excellent, 4 = poor); null = not rated. */
  rqi: number | null
  /** Continuous score behind the class (same 1–4 scale). */
  score: number | null
  /** Calibrated probability that the road is bad (0–1). */
  pBad: number | null
  /** 0–1; how much the estimate can be trusted. */
  confidence: number
  /** 'high' | 'medium' | 'low' (kept as string: tolerate unknown values). */
  confidenceLevel: ConfidenceLevel | (string & {})
  /**
   * Why the confidence is not high: 'few_images' | 'disagreement' |
   * 'near_threshold' | 'old_images' | 'unlabelled_area'; null when high.
   */
  confidenceReason?: string | null
  /** Number of Street View frames the estimate is based on. */
  nImages: number
  lengthM: number
  roadName: string | null
  /** OSM highway tag (residential, primary, ...). */
  highway: string | null
  /** Oldest / newest Street View capture month, "YYYY-MM". */
  captureDateMin: string | null
  captureDateMax: string | null
}

export interface RouteQuality {
  totalLengthM: number
  coveredLengthM: number
  /** Metres of the route in quality class 1..4 (index 0 = class 1). */
  lengthByRqi: number[]
  meanScore: number | null
  /** Speed-weighted impact (lower = better, 0 = all Kiváló); ranks "Legsimább". */
  impactScore?: number | null
  worstSegments: RoadSegment[]
}

/** South-west / north-east corners, as Leaflet's fitBounds takes them. */
export type Bounds = [LatLng, LatLng]

export interface RoadSegmentsState {
  /** Segments of the current viewport (zoom >= SEGMENT_MIN_ZOOM). */
  items: RoadSegment[]
  loading: boolean
  error: string | null
  /** False once the backend turned out not to know `roadSegments` (older
   *  deploy) — the map then falls back to the legacy grid/points split. */
  supported: boolean
  /** Last viewport query, kept so the layer can be refreshed after a job. */
  lastQuery: { bbox: number[]; zoom: number } | null
  /** The whole object, not an id: a segment picked from the route summary
   *  need not be part of the viewport list. */
  selected: RoadSegment | null
  /** Frame dots near the selected segment (inspection below the dot zoom). */
  frames: RoadPoint[]
  routeQuality: RouteQuality | null
  routeQualityLoading: boolean
  routeQualityError: string | null
  /** One-shot "fit the map to these bounds" request; seq makes repeats distinct. */
  focus: { bounds: Bounds; seq: number } | null
}
