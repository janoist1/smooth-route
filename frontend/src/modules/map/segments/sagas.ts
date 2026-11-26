import { call, delay, put, select, takeLatest } from 'redux-saga/effects'
import type { SagaIterator } from 'redux-saga'
import { takeLatestAsync } from 'saga-toolkit'
import type { SagaPendingAction } from 'saga-toolkit'
import { gqlQuery } from '../../graphql'
import { actions as mapActions } from '../slice'
import * as mapSelectors from '../selectors'
import { rankRouteAlternatives, type RouteAlternative } from '../alternatives'
import type { RoadPoint } from '../types'
import { actions, fetchRouteQuality, fetchSegmentFrames, fetchSegments } from './slice'
import * as selectors from './selectors'
import * as api from './api'
import { layersForZoom } from './style'
import type { LatLng, RoadSegment, RouteQuality } from './types'

/** Quiet time after the last map move before the segment request is sent. */
export const SEGMENT_FETCH_DEBOUNCE_MS = 250

type SegmentMocks = Awaited<ReturnType<typeof api.loadSegmentMocks>>

// Debounce + cancel in one: takeLatestAsync cancels the previous worker on
// every new request, so while the user keeps panning each worker dies in its
// `delay` and only the last viewport reaches the network.
export function* fetchSegmentsWorker(action: SagaPendingAction<typeof fetchSegments>) {
  const { bbox, zoom } = action.meta.arg
  yield delay(SEGMENT_FETCH_DEBOUNCE_MS)

  if (api.segmentMocksEnabled()) {
    const mocks: SegmentMocks = yield call(api.loadSegmentMocks)
    return mocks.mockRoadSegments(bbox, zoom)
  }

  try {
    const data = yield* gqlQuery({ query: api.GET_ROAD_SEGMENTS, variables: { bbox, zoom } })
    return data.roadSegments ?? []
  } catch (error) {
    if (!api.isUnknownFieldError(error, 'roadSegments')) throw error
    // Older backend without the segment API: remember it and load what the
    // legacy view shows at this zoom instead, so the map is never empty.
    yield put(actions.markUnsupported())
    if (layersForZoom(zoom, false).grid) yield put(mapActions.fetchGrid({ bbox, zoom }))
    else yield put(mapActions.fetchPoints(bbox))
    return [] as RoadSegment[]
  }
}

// Frames belonging to the selected segment, for inspection below
// the zoom where all dots show. Optional extra: a failure just means no dots.
export function* fetchSegmentFramesWorker(action: SagaPendingAction<typeof fetchSegmentFrames>) {
  const segment = action.meta.arg
  try {
    const data = yield* gqlQuery({
      query: api.GET_SEGMENT_FRAMES,
      variables: { segmentId: segment.id },
    })
    return (data.segmentFrames ?? []).map((p): RoadPoint => ({
      id: p.id,
      latitude: p.latitude,
      longitude: p.longitude,
      heading: p.heading ?? undefined,
      // Same mapping as the viewport dots (../sagas.ts) so both colour alike.
      rqi_score: p.rqiScore ?? undefined,
      rqi_source: p.rqiSource ?? undefined,
      capture_date: p.captureDate,
    }))
  } catch (error) {
    console.warn('Segment frames could not be loaded:', error)
    return [] as RoadPoint[]
  }
}

export function* fetchRouteQualityWorker(action: SagaPendingAction<typeof fetchRouteQuality>) {
  return yield* loadRouteQuality(action.meta.arg)
}

function* loadRouteQuality(path: LatLng[]) {
  if (api.segmentMocksEnabled()) {
    const mocks: SegmentMocks = yield call(api.loadSegmentMocks)
    return mocks.mockRouteQuality(path) as RouteQuality | null
  }

  try {
    const data = yield* gqlQuery({ query: api.GET_ROUTE_QUALITY, variables: { path } })
    return data.routeQuality as RouteQuality | null
  } catch (error) {
    // Backend without routeQuality: no summary rather than an error message.
    if (api.isUnknownFieldError(error, 'routeQuality')) return null
    throw error
  }
}

// A planned route immediately gets its quality summary.
export function* onRoutePlanned(
  action: ReturnType<typeof mapActions.planRoute.fulfilled>,
): SagaIterator {
  if (action.payload?.length > 1) yield put(actions.fetchRouteQuality(action.payload))
}

// Picking another alternative: its full quality summary (incl. worst segments).
export function* onRouteAlternativeSelected(): SagaIterator {
  const route: LatLng[] | null = yield select(mapSelectors.selectRoutePoints)
  if (route && route.length > 1) yield put(actions.fetchRouteQuality(route))
}

// Selecting a segment closes an open point card and loads the segment's frames.
export function* onSegmentSelected(
  action: ReturnType<typeof actions.selectSegment | typeof actions.focusSegment>,
): SagaIterator {
  if (!action.payload) return
  yield put(mapActions.selectPoint(null))
  yield put(actions.fetchSegmentFrames(action.payload))
}

// A finished route-analysis job changed the data: refresh what is on screen.
export function* onAnalysisFinished(): SagaIterator {
  const supported: boolean = yield select(selectors.selectSegmentsSupported)
  const viewport: { zoom: number } = yield select(mapSelectors.selectViewport)
  const lastQuery: { bbox: number[]; zoom: number } | null = yield select(
    selectors.selectLastSegmentQuery,
  )
  if (lastQuery && layersForZoom(viewport.zoom, supported).segments) {
    yield put(actions.fetchSegments(lastQuery))
  }
  const route: LatLng[] | null = yield select(mapSelectors.selectRoutePoints)
  if (supported && route && route.length > 1) yield put(actions.fetchRouteQuality(route))
  if (!supported) return

  const segment: RoadSegment | null = yield select(selectors.selectSelectedSegment)
  if (segment) yield put(actions.fetchSegmentFrames(segment))

  const alternatives: RouteAlternative[] | null = yield select(mapSelectors.selectRouteAlternatives)
  if (!alternatives?.length) return
  try {
    const refreshed: RouteAlternative[] = []
    for (const alternative of alternatives) {
      const quality: RouteQuality | null = yield call(loadRouteQuality, alternative.points)
      if (!quality) return
      refreshed.push({ ...alternative, quality })
    }
    // Selection can change while requests run. Keep the current choice, and
    // discard results if a new plan replaced or cleared these alternatives.
    const current: RouteAlternative[] | null = yield select(mapSelectors.selectRouteAlternatives)
    if (current !== alternatives) return
    const selected: number | null = yield select(mapSelectors.selectSelectedRouteIndex)
    yield put(
      mapActions.setRouteAlternatives({ routes: rankRouteAlternatives(refreshed), selected }),
    )
  } catch (error) {
    console.warn('Route alternatives could not be refreshed:', error)
  }
}

export default [
  takeLatestAsync(fetchSegments, fetchSegmentsWorker),
  takeLatestAsync(fetchSegmentFrames, fetchSegmentFramesWorker),
  takeLatestAsync(fetchRouteQuality, fetchRouteQualityWorker),
  takeLatest(mapActions.planRoute.fulfilled.type, onRoutePlanned),
  takeLatest(mapActions.selectRouteAlternative.type, onRouteAlternativeSelected),
  takeLatest([actions.selectSegment.type, actions.focusSegment.type], onSegmentSelected),
  takeLatest(
    [mapActions.finishAnalysis.type, mapActions.planRoute.pending.type, mapActions.clearRoute.type],
    function* (action: { type: string }): SagaIterator {
      if (mapActions.finishAnalysis.match(action)) yield* onAnalysisFinished()
    },
  ),
]
