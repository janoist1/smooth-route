import { call, put, takeLatest, select, takeEvery } from 'redux-saga/effects'
import { actions } from './slice'
import { client, gql } from '../graphql'
import type { RootState } from '../../store'
import * as selectors from './selectors'
import type { GetPointsQuery, GetPointDetailQuery, GetRouteQuery, ProcessRouteMutation } from '../graphql/generated/graphql'

// Fragment Colocation: Define what we need
// Inlined for simplicity to satisfy linter
const GET_POINTS = gql(`
  query GetPoints($limit: Int, $bbox: [Float!]) {
    points(limit: $limit, bbox: $bbox) {
      id
      latitude
      longitude
      rqiScore
      heading
    }
  }
`)

const GET_POINT_DETAIL = gql(`
  query GetPointDetail($id: Int!) {
    point(id: $id) {
      id
      latitude
      longitude
      rqiScore
      heading
      pitch
      imageUrl
      # manual data
      manualRqi
      manualTags
      manualAnnotations
      # analysis
      damageCount
      damageTypes
      analysisMetadata
      createdAt
    }
  }
`)

const GET_ROUTE = gql(`
  query GetRoute($origin: String!, $destination: String!) {
    getRoute(origin: $origin, destination: $destination) {
      points {
        lat
        lng
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

import { takeLatestAsync } from 'saga-toolkit'
import type { SagaActionFromCreator } from 'saga-toolkit'

// Backend endpoint: GET /api/v1/points
function* fetchPointsWorker(action: SagaActionFromCreator<typeof actions.fetchPoints>) {
  const bbox = action.meta.arg

  const result: { data: GetPointsQuery } = yield call([client, client.query], {
    query: GET_POINTS,
    variables: { limit: 2000, bbox },
  })

  return result.data.points.map(p => ({
    id: p.id,
    latitude: p.latitude,
    longitude: p.longitude,
    heading: p.heading,
    rqi_score: p.rqiScore ?? undefined,
  }))
}

function* fetchPointDetailWorker(action: SagaActionFromCreator<typeof actions.fetchPointDetail>) {
  const id = action.meta.arg
  const result: { data: GetPointDetailQuery } = yield call([client, client.query], {
    query: GET_POINT_DETAIL,
    variables: { id },
  })

  const pt = result.data.point
  if (!pt) throw new Error('Point not found')

  return {
    id: pt.id,
    latitude: pt.latitude,
    longitude: pt.longitude,
    heading: pt.heading,
    pitch: pt.pitch,
    rqi_score: pt.rqiScore,
    damage_count: pt.damageCount,
    damage_types: pt.damageTypes,
    analysis_metadata: pt.analysisMetadata,
    image_url: pt.imageUrl,
    created_at: pt.createdAt,
    manual_rqi: pt.manualRqi,
    manual_tags: pt.manualTags,
    manual_annotations: pt.manualAnnotations,
  }
}

function* planRouteWorker(action: SagaActionFromCreator<typeof actions.planRoute>) {
  const { origin, destination } = action.meta.arg
  
  const result: { data: GetRouteQuery } = yield call([client, client.query], {
    query: GET_ROUTE,
    variables: { origin, destination },
  })
  
  if (!result.data) {
    throw new Error('Hiba a szerver kommunikációban (No Data)')
  }

  const routeData = result.data.getRoute
  if (!routeData) throw new Error('Route not found')
    
  return routeData.points.map(p => [p.lat, p.lng] as [number, number])
}

function* analyzeRouteWorker(action: SagaActionFromCreator<typeof actions.analyzeRoute>) {
  const { origin, destination } = action.meta.arg
  
  const result: { data: ProcessRouteMutation } = yield call([client, client.mutate], {
    mutation: PROCESS_ROUTE,
    variables: {
      input: {
        origin,
        destination
      }
    }
  })
  
  return result.data.processRoute.id
}

import { actions as apiActions } from '../api'

// ...

// eslint-disable-next-line @typescript-eslint/no-explicit-any
function* watchJobStart(action: any) {
    const jobId = action.payload
    // Register the job in the global API module, which will start the polling loop
    yield put(apiActions.registerJob(jobId))
}


// React to selection: If selected, fetch details
function* handleSelectionSaga(action: ReturnType<typeof actions.selectPoint>) {
  if (action.payload !== null) {
    yield put(actions.fetchPointDetail(action.payload))
  }
}

// Listen for job updates to trigger refetch upon completion
function* watchJobUpdates(action: ReturnType<typeof apiActions.updateJob>) {
  const { id, status } = action.payload

  // Check if this is our analysis job
  const routeJobId: string | null = yield select((state: RootState) => state.map.routeAnalysisJobId)

  if (id === routeJobId && status === 'completed') {
    // Job finished! Refetch points to show new data
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
    yield put(actions.fetchPoints(bbox))
    yield put(actions.finishAnalysis())
  }
}

export default [
  takeLatestAsync(actions.fetchPoints.type, fetchPointsWorker),
  takeLatestAsync(actions.fetchPointDetail.type, fetchPointDetailWorker),
  takeLatest(actions.selectPoint.type, handleSelectionSaga),
  takeLatestAsync(actions.planRoute.type, planRouteWorker),
  takeLatestAsync(actions.analyzeRoute.type, analyzeRouteWorker),
  // Use toString() to be safe if it's an action creator or string
  takeLatest(actions.analyzeRoute.fulfilled.toString(), watchJobStart),
  takeEvery(apiActions.updateJob.type, watchJobUpdates),
]
