// Road-segment API documents (GraphQL). The backend for these queries is being
// built in parallel, so the result/variable types are HAND-WRITTEN here against
// the agreed contract instead of coming from src/modules/graphql/generated/.
// Each document is typed as a TypedDocumentNode, so the saga helpers
// (gqlQuery / gqlQueryResult) infer results and variables from it.
//
// After the backend is merged and `npm run codegen` has run, `gql('<source>')`
// resolves to the generated documents by itself (the sources are plain
// literals); the hand-written `*Data` / `*Variables` types and the casts can
// then be dropped.
import type { TypedDocumentNode } from '@graphql-typed-document-node/core'
import { gql } from '../../graphql'
import type { LatLng, RoadSegment, RouteQuality } from './types'

// --- Documents --------------------------------------------------------------

export interface RoadSegmentsData {
  roadSegments: RoadSegment[]
}
export interface RoadSegmentsVariables {
  /** [minLng, minLat, maxLng, maxLat] — same order as roadQualityGrid. */
  bbox: number[]
  zoom: number
}

export const GET_ROAD_SEGMENTS = gql(`
  query GetRoadSegments($bbox: [Float!]!, $zoom: Int!) {
    roadSegments(bbox: $bbox, zoom: $zoom) {
      id
      path
      rqi
      score
      pBad
      confidence
      confidenceLevel
      confidenceReason
      nImages
      lengthM
      roadName
      highway
      captureDateMin
      captureDateMax
    }
  }
`) as unknown as TypedDocumentNode<RoadSegmentsData, RoadSegmentsVariables>

export interface RouteQualityData {
  routeQuality: RouteQuality
}
export interface RouteQualityVariables {
  /** [[lat, lng], ...] exactly as planRoute returns it. */
  path: LatLng[]
}

export const GET_ROUTE_QUALITY = gql(`
  query GetRouteQuality($path: [[Float!]!]!) {
    routeQuality(path: $path) {
      totalLengthM
      coveredLengthM
      lengthByRqi
      meanScore
      impactScore
      meanRqi
      worstSegments {
        id
        path
        rqi
        score
        pBad
        confidence
        confidenceLevel
        confidenceReason
        nImages
        lengthM
        roadName
        highway
        captureDateMin
        captureDateMax
      }
    }
  }
`) as unknown as TypedDocumentNode<RouteQualityData, RouteQualityVariables>

// Membership, heading and usability are resolved by the segment builder's rule.
export interface SegmentFramesData {
  segmentFrames: Array<{
    id: number
    latitude: number
    longitude: number
    rqiScore?: number | null
    rqiSource?: string | null
    heading?: number | null
    captureDate?: string | null
  }>
}
export interface SegmentFramesVariables {
  segmentId: string
}

export const GET_SEGMENT_FRAMES = gql(`
  query GetSegmentFrames($segmentId: ID!) {
    segmentFrames(segmentId: $segmentId) {
      id
      latitude
      longitude
      rqiScore
      rqiSource
      heading
      captureDate
    }
  }
`) as unknown as TypedDocumentNode<SegmentFramesData, SegmentFramesVariables>

// --- Errors -----------------------------------------------------------------

/** The backend's schema has no segment API yet (older deploy). */
export class SegmentApiUnsupportedError extends Error {
  constructor(field: string) {
    super(`The server does not know the ${field} query yet`)
    this.name = 'SegmentApiUnsupportedError'
  }
}

/** All message texts of an Apollo / GraphQL / HTTP error, in one string. */
export const errorText = (error: unknown): string => {
  if (!error) return ''
  if (typeof error === 'string') return error
  const e = error as { message?: unknown; errors?: unknown; result?: unknown; bodyText?: unknown }
  // Apollo wraps GraphQL / HTTP errors in different shapes; collect all texts.
  const parts = [e.message, e.bodyText]
  if (Array.isArray(e.errors)) {
    parts.push(...e.errors.map(x => (x as { message?: unknown } | null)?.message))
  }
  if (e.result) parts.push(typeof e.result === 'string' ? e.result : JSON.stringify(e.result))
  return parts.filter((p): p is string => typeof p === 'string').join(' | ')
}

/** True when the error is GraphQL validation rejecting an unknown `field`. */
export const isUnknownFieldError = (error: unknown, field: string): boolean => {
  const text = errorText(error)
  return /cannot query field/i.test(text) && text.includes(field)
}

// --- Mock toggle (visual checks before the backend exists) -------------------

/**
 * Mock data instead of the network when `VITE_MOCK_SEGMENTS=1` is set, or — in
 * the dev server only — when the page URL carries `?mockSegments=1`.
 */
export const segmentMocksEnabled = (): boolean => {
  if (import.meta.env.VITE_MOCK_SEGMENTS === '1') return true
  if (!import.meta.env.DEV || typeof window === 'undefined') return false
  return new URLSearchParams(window.location.search).get('mockSegments') === '1'
}

/** Lazy-loaded mock module: never part of the main production chunk. */
export const loadSegmentMocks = () => import('./mock')
