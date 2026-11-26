import { useMemo } from 'react'
import { useDispatch, useSelector } from 'react-redux'
import { actions } from './slice'
import * as selectors from './selectors'
import type { RoadPoint } from '../types'
import type { Bounds, RoadSegment, RouteQuality } from './types'

// Controller hook: the only way components reach the road-segment state.
export interface UseRoadSegments {
  /** Segments of the current viewport. */
  segments: RoadSegment[]
  segmentsLoading: boolean
  /** The last segment request failed (not a cancelled one). */
  segmentsError: string | null
  /** A request finished and this area simply has no measured roads. */
  segmentsEmpty: boolean
  /** False when the backend has no segment API (legacy grid/points view). */
  segmentsSupported: boolean
  selectedSegment: RoadSegment | null
  /** Frame dots near the selected segment. */
  segmentFrames: RoadPoint[]
  routeQuality: RouteQuality | null
  routeQualityLoading: boolean
  routeQualityError: string | null
  /** One-shot request to fit the map to a segment. */
  segmentFocus: { bounds: Bounds; seq: number } | null

  selectSegment: (segment: RoadSegment | null) => void
  /** Select + fit the map to the segment (used by the route summary list). */
  focusSegment: (segment: RoadSegment) => void
}

export const useRoadSegments = (): UseRoadSegments => {
  const dispatch = useDispatch()

  const segments = useSelector(selectors.selectSegments)
  const segmentsLoading = useSelector(selectors.selectSegmentsLoading)
  const segmentsError = useSelector(selectors.selectSegmentsError)
  const lastQuery = useSelector(selectors.selectLastSegmentQuery)
  const segmentsSupported = useSelector(selectors.selectSegmentsSupported)
  const selectedSegment = useSelector(selectors.selectSelectedSegment)
  const segmentFrames = useSelector(selectors.selectSegmentFrames)
  const routeQuality = useSelector(selectors.selectRouteQuality)
  const routeQualityLoading = useSelector(selectors.selectRouteQualityLoading)
  const routeQualityError = useSelector(selectors.selectRouteQualityError)
  const segmentFocus = useSelector(selectors.selectSegmentFocus)

  const bound = useMemo(
    () => ({
      selectSegment: (segment: RoadSegment | null) => {
        dispatch(actions.selectSegment(segment))
      },
      focusSegment: (segment: RoadSegment) => {
        dispatch(actions.focusSegment(segment))
      },
    }),
    [dispatch],
  )

  return {
    segments,
    segmentsLoading,
    segmentsError,
    segmentsEmpty:
      lastQuery !== null && !segmentsLoading && !segmentsError && segments.length === 0,
    segmentsSupported,
    selectedSegment,
    segmentFrames,
    routeQuality,
    routeQualityLoading,
    routeQualityError,
    segmentFocus,
    ...bound,
  }
}
