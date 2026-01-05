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

// React to selection: If selected, fetch details
function* handleSelectionSaga(action: ReturnType<typeof actions.selectPoint>) {
  if (action.payload !== null) {
    yield put(actions.fetchPointDetail(action.payload))
  }
}

export default [
  takeLatestAsync(actions.fetchPoints.type, fetchPointsWorker),
  takeLatestAsync(actions.fetchPointDetail.type, fetchPointDetailWorker),
  takeLatest(actions.selectPoint.type, handleSelectionSaga),
]
