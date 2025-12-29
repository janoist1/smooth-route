import { call, put, takeLatest } from 'redux-saga/effects'
import { actions } from './slice'
import { client, gql } from '../graphql'
import type { GetPointsQuery, GetPointDetailQuery } from '../graphql/generated/graphql'

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

// Backend endpoint: GET /api/v1/points
function* fetchPointsSaga(action: ReturnType<typeof actions.fetchPoints>) {
  try {
    const bbox = action.payload

    const result: { data: GetPointsQuery } = yield call([client, client.query], {
      query: GET_POINTS,
      variables: { limit: 2000, bbox },
    })

    // Map GraphQL result to Redux state shape
    // Note: The types might slightly mismatch (camelCase vs snake_case).
    // Our GraphQL schema uses snake_case by default or camelCase?
    // Strawberry uses snake_case in Python, but camelCase in JSON by default usually unless configured.
    // Let's check codegen output or safely assume camelCase for GraphQL fields.

    // Wait, Strawberry default is camelCase for fields.
    // REST API returned snake_case or camelCase? Pydantic used snake_case.
    // Frontend likely expects whatever REST returned.
    // Let's assume we might need a mapping layer if frontend relies on snake_case.
    // Checking PointResponse in routes.py -> snake_case keys (rqi_score).
    // Checking previous map/slice.ts -> defined as snake_case probably?
    // Let's look at PointCore fields above: rqiScore.
    // We probably need to map back to snake_case if the slice expects it.

    const points = result.data.points.map(p => ({
      id: p.id,
      latitude: p.latitude,
      longitude: p.longitude,
      heading: p.heading,
      rqi_score: p.rqiScore ?? undefined,
    }))

    yield put(actions.fetchPointsSuccess(points))
  } catch (error: unknown) {
    console.error('Failed to fetch points', error)
    const msg = error instanceof Error ? error.message : 'Unknown error'
    yield put(actions.fetchPointsFailure(msg))
  }
}

function* fetchPointDetailSaga(action: ReturnType<typeof actions.fetchPointDetail>) {
  try {
    const id = action.payload
    const result: { data: GetPointDetailQuery } = yield call([client, client.query], {
      query: GET_POINT_DETAIL,
      variables: { id },
    })

    const pt = result.data.point
    if (!pt) throw new Error('Point not found')

    // Map to expected detail shape
    // REST returned: { id, latitude, longitude, heading, pitch, rqi_score, damage_count, damage_types ... }
    const detail = {
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
      // Manual data is now here too!
      manual_rqi: pt.manualRqi,
      manual_tags: pt.manualTags,
      manual_annotations: pt.manualAnnotations,
    }

    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    yield put(actions.fetchPointDetailSuccess(detail as any))
  } catch (error: unknown) {
    console.error('Failed to fetch details', error)
    // If needed, dispatch failure
  }
}

// React to selection: If selected, fetch details
function* handleSelectionSaga(action: ReturnType<typeof actions.selectPoint>) {
  if (action.payload !== null) {
    yield put(actions.fetchPointDetail(action.payload))
  }
}

export default [
  takeLatest(actions.fetchPoints.type, fetchPointsSaga),
  takeLatest(actions.selectPoint.type, handleSelectionSaga),
  takeLatest(actions.fetchPointDetail.type, fetchPointDetailSaga),
]
