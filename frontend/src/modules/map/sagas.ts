import { put, takeLatest, select, takeEvery } from 'redux-saga/effects'
import { defaultRouteIndex, routePlanErrorMessage, type RouteAlternative } from './alternatives'
import type { SagaIterator } from 'redux-saga'
import { takeLatestAsync } from 'saga-toolkit'
import type { SagaActionFromCreator } from 'saga-toolkit'
import { actions } from './slice'
import { actions as apiActions } from '../api'
import { gql, gqlMutate, gqlQuery, gqlQueryResult } from '../graphql'
import type { RootState } from '../../store'
import * as selectors from './selectors'
import type { QualityGrid } from './aggregation'
import { shouldShowGrid } from './aggregation'

// Fragment Colocation: Define what we need
// Inlined for simplicity to satisfy linter
const GET_POINTS = gql(`
  query GetPoints($limit: Int, $bbox: [Float!]) {
    points(limit: $limit, bbox: $bbox) {
      id
      latitude
      longitude
      rqiScore
      dinoRqiScore
      rqiSource
      heading
      captureDate
    }
  }
`)

const GET_ROAD_QUALITY_GRID = gql(`
  query GetRoadQualityGrid($zoom: Int!, $bbox: [Float!]) {
    roadQualityGrid(zoom: $zoom, bbox: $bbox)
  }
`)

const GET_POINT_DETAIL = gql(`
  query GetPointDetail($id: Int!) {
    point(id: $id) {
      id
      latitude
      longitude
      rqiScore
      dinoRqiScore
      dinoScore
      dinoPBad
      rqiSource
      heading
      pitch
      imageUrl
      streetViewUrl
      captureDate
      # manual data
      manualRqi
      manualTags
      manualAnnotations
# ...
      # analysis
      damageCount
      damageTypes
      analysisMetadata
      createdAt
    }
  }
`)

// One routing call per plan (alternatives=true); every route comes
// with its road quality from the stored segments.
const ROUTE_ALTERNATIVES = gql(`
  query RouteAlternatives($origin: String!, $destination: String!) {
    routingProvider
    routeAlternatives(origin: $origin, destination: $destination) {
      fastestIndex
      smoothestIndex
      routes {
        index
        distanceM
        durationS
        summary
        coverage
        isFastest
        isSmoothest
        smoothestConfident
        points {
          lat
          lng
        }
        quality {
          totalLengthM
          coveredLengthM
          lengthByRqi
          meanScore
          meanRqi
          impactScore
        }
      }
    }
  }
`)

const PROCESS_ROUTE = gql(`
  mutation ProcessRoute($input: ProcessRouteInput!) {
    processRoute(input: $input) {
      id
      status
      message
    }
  }
`)

// Shared with training; only fields available on the public status type.
const GET_ACTIVE_JOB = gql(`
    query GetActiveJob {
        activeJob {
            id
            status
            progress
            total
        }
    }
`)

// Individual points only load zoomed in (zoom ≥ 14), where the viewport bbox
// is small — the bbox is the real bound, so this cap only exists to stop a
// pathological query returning the whole table. Points render on a canvas
// (preferCanvas) so a few thousand in a dense city view stay smooth.
const MAP_POINT_LIMIT = 20000

function* fetchPointsWorker(action: SagaActionFromCreator<typeof actions.fetchPoints>) {
  const bbox = action.meta.arg

  const data = yield* gqlQuery({
    query: GET_POINTS,
    variables: { limit: MAP_POINT_LIMIT, bbox },
  })

  return data.points.map(p => ({
    id: p.id,
    latitude: p.latitude,
    longitude: p.longitude,
    heading: p.heading,
    rqi_score: p.rqiScore ?? undefined,
    rqi_source: p.rqiSource,
    capture_date: p.captureDate,
  }))
}

// Backend: GraphQL roadQualityGrid — { cell, cells: [[swLat, swLng, avgRqi]] }.
function* fetchGridWorker(action: SagaActionFromCreator<typeof actions.fetchGrid>) {
  const { bbox, zoom } = action.meta.arg

  const data = yield* gqlQuery({
    query: GET_ROAD_QUALITY_GRID,
    variables: { zoom, bbox },
  })

  return (data.roadQualityGrid ?? { cell: 0, cells: [] }) as QualityGrid
}

function* fetchPointDetailWorker(action: SagaActionFromCreator<typeof actions.fetchPointDetail>) {
  const id = action.meta.arg
  const data = yield* gqlQuery({
    query: GET_POINT_DETAIL,
    variables: { id },
  })

  const pt = data.point
  if (!pt) throw new Error('Point not found')

  return {
    id: pt.id,
    latitude: pt.latitude,
    longitude: pt.longitude,
    heading: pt.heading,
    pitch: pt.pitch,
    rqi_score: pt.rqiScore,
    dino_rqi_score: pt.dinoRqiScore,
    dino_score: pt.dinoScore,
    dino_p_bad: pt.dinoPBad,
    rqi_source: pt.rqiSource,
    damage_count: pt.damageCount,
    damage_types: pt.damageTypes,
    analysis_metadata: pt.analysisMetadata,
    image_url: pt.imageUrl,
    street_view_url: pt.streetViewUrl,
    capture_date: pt.captureDate,
    created_at: pt.createdAt,
    manual_rqi: pt.manualRqi,
    manual_tags: pt.manualTags,
    manual_annotations: pt.manualAnnotations,
  }
}

function* planRouteWorker(action: SagaActionFromCreator<typeof actions.planRoute>) {
  const { origin, destination } = action.meta.arg
  
  const result = yield* gqlQueryResult({
    query: ROUTE_ALTERNATIVES,
    variables: { origin, destination },
  })

  if (!result.data?.routeAlternatives) {
    throw new Error(routePlanErrorMessage(result.error))
  }

  const res = result.data.routeAlternatives
  const provider = result.data.routingProvider
  const routes: RouteAlternative[] = res.routes.map(r => ({
    provider,
    index: r.index,
    points: r.points.map(p => [p.lat, p.lng] as [number, number]),
    distanceM: r.distanceM,
    durationS: r.durationS,
    summary: r.summary,
    quality: { ...r.quality, worstSegments: [] },
    coverage: r.coverage,
    isFastest: r.isFastest,
    isSmoothest: r.isSmoothest,
    smoothestConfident: r.smoothestConfident,
  }))
  const selected = defaultRouteIndex({ routes, fastestIndex: res.fastestIndex ?? null, smoothestIndex: res.smoothestIndex ?? null })
  const chosen = routes.find(r => r.index === selected)
  if (!chosen) throw new Error('Route not found')
  yield put(actions.setRouteAlternatives({ routes, selected }))
  return chosen.points
}

function* analyzeRouteWorker(action: SagaActionFromCreator<typeof actions.analyzeRoute>) {
  const { origin, destination } = action.meta.arg
  const path: [number, number][] | null = yield select(selectors.selectRoutePoints)
  if (!path || path.length < 2) throw new Error('Előbb válassz egy útvonalat')
  
  const data = yield* gqlMutate({
    mutation: PROCESS_ROUTE,
    variables: {
      input: {
        origin,
        destination,
        path,
      }
    }
  })
  
  return data.processRoute.id
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
function* watchJobStart(action: any) {
    const jobId = action.payload
    // Register the job in the global API module, which will start the polling loop
    yield put(apiActions.registerJob(jobId))
}

// On map load, re-attach to a route job still running on the backend so the
// progress UI survives a page reload (routeAnalysisJobId lives only in memory).
function* reconnectRouteJobSaga(): SagaIterator {
  try {
    const result = yield* gqlQueryResult({
      query: GET_ACTIVE_JOB,
      fetchPolicy: 'network-only',
    })

    const job = result.data?.activeJob
    if (!job) return

    const status = String(job.status).toLowerCase()
    const done = status === 'completed' || status === 'failed' || status === 'cancelled'
    if (done) return
    if (job.total > 0 && job.progress >= job.total) return

    yield put(actions.restoreRouteJob(job.id))
    yield put(apiActions.registerJob(job.id))
  } catch (err) {
    console.error('Failed to reconnect route job:', err)
  }
}


// React to selection: If selected, fetch details
function* handleSelectionSaga(action: ReturnType<typeof actions.selectPoint>) {
  if (action.payload !== null) {
    yield put(actions.fetchPointDetail(action.payload))
  }
}

// Listen for job updates to trigger refetch upon completion
function* watchJobUpdates(action: ReturnType<typeof apiActions.updateJob>): SagaIterator {
  const { id, status } = action.payload

  // Check if this is our analysis job
  const routeJobId: string | null = yield select((state: RootState) => state.map.routeAnalysisJobId)

  if (id === routeJobId && status === 'completed') {
    // Job finished! Refetch to show new data — respect the zoom-based
    // aggregate/raw split so a zoomed-out refresh isn't silently truncated.
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const viewport: any = yield select(selectors.selectViewport)
    const { center, zoom } = viewport

    // Reuse BBox logic
    const width = typeof window !== 'undefined' ? window.innerWidth : 1024
    const height = typeof window !== 'undefined' ? window.innerHeight : 768
    const degPerPixel = 360 / (Math.pow(2, zoom) * 256)
    const lngDelta = (width / 2) * degPerPixel
    const latDelta = (height / 2) * degPerPixel

    const bbox = [
      center[1] - lngDelta,
      center[0] - latDelta,
      center[1] + lngDelta,
      center[0] + latDelta,
    ]
    if (shouldShowGrid(zoom)) {
      yield put(actions.fetchGrid({ bbox, zoom }))
    } else {
      yield put(actions.fetchPoints(bbox))
    }
    yield put(actions.finishAnalysis())
  }
}

export default [
  // saga-toolkit dispatches the RTK pending action, so subscribe to its type
  // (createSagaAction only exposes `.type` at runtime, not in the types).
  takeLatestAsync(actions.fetchPoints.pending.type, fetchPointsWorker),
  takeLatestAsync(actions.fetchGrid.pending.type, fetchGridWorker),
  takeLatestAsync(actions.fetchPointDetail.pending.type, fetchPointDetailWorker),
  takeLatest(actions.selectPoint.type, handleSelectionSaga),
  takeLatestAsync(
    [actions.planRoute.pending.type, actions.clearRoute.type],
    function* (action: SagaActionFromCreator<typeof actions.planRoute> | ReturnType<typeof actions.clearRoute>) {
      if (actions.clearRoute.match(action)) return
      return yield* planRouteWorker(action)
    },
  ),
  takeLatestAsync(actions.analyzeRoute.pending.type, analyzeRouteWorker),
  // Use toString() to be safe if it's an action creator or string
  takeLatest(actions.analyzeRoute.fulfilled.toString(), watchJobStart),
  takeLatest(actions.reconnectRouteJob.type, reconnectRouteJobSaga),
  takeEvery(apiActions.updateJob.type, watchJobUpdates),
]
