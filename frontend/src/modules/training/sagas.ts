import { call, select, put, takeLatest } from 'redux-saga/effects'

import { actions, fetchImage, fetchList, fetchStats } from './slice'
import type { Annotation, TrainingPoint, TrainingStats } from './types'

import { takeLatestAsync } from 'saga-toolkit'
import type { SagaActionFromCreator } from 'saga-toolkit'
import { client, gql } from '../graphql'
import type {
  GetTrainingDataQuery,
  GetActiveJobQuery,
} from '../graphql/generated/graphql'
import { selectTrainingState } from './selectors'
import { actions as apiActions } from '../api'

// --- GraphQL Queries & Mutations ---

interface ReviewActionResult {
    success: boolean
    message?: string
    processedImageUrl?: string
    annotations?: Annotation[]
}

const GET_TRAINING_DATA = gql(`
    query GetTrainingData($id: Int!) {
        point(id: $id) {
            imageUrl
            manualRqi
            manualTags
            manualAnnotations
            manualComment
        }
    }
`)

const SAVE_TRAINING_DATA = gql(`
    mutation SaveTrainingData($input: TrainingDataInput!) {
        saveTrainingData(input: $input)
    }
`)

const DELETE_TRAINING_DATA = gql(`
    mutation DeleteTrainingData($imageFilename: String!) {
        deleteTrainingData(imageFilename: $imageFilename)
    }
`)

const GET_TRAINING_POINTS = gql(`
  query GetTrainingPoints($mode: FilterMode, $limit: Int, $offset: Int, $model: String) {
    trainingPoints(mode: $mode, limit: $limit, offset: $offset, model: $model) {
      items {
        id
        latitude
        longitude
        imageUrl
        rqiScore
        dinoRqiScore
        manualRqi
      }
      totalCount
      hasMore
    }
  }
`)

const GET_TRAINING_STATS = gql(`
  query GetTrainingStats($mode: FilterMode, $isDino: Boolean) {
    trainingStats(mode: $mode, isDino: $isDino) {
      total
      pending
      annotated
      avgRqi
      goodCount
      fairCount
      poorCount
      pendingAnalysis
      rqi1Count
      rqi2Count
      rqi3Count
      rqi4Count
      rqi5Count
    }
  }
`)

const RUN_ANALYSIS = gql(`
    mutation RunAnalysis($input: RunAnalysisInput!) {
        runAnalysis(input: $input) {
            id
        }
    }
`)

const START_MODEL_TRAINING = gql(`
    mutation StartModelTraining {
        startModelTraining {
            id
        }
    }
`)

const STOP_JOB = gql(`
    mutation StopJob($jobId: String!) {
        stopJob(jobId: $jobId)
    }
`)

const GET_ACTIVE_JOB = gql(`
    query GetActiveJob {
        activeJob {
            id
            type
            status
            progress
            total
            details
            result
        }
    }
`)





// Logic to fetch image from API
function* fetchImageWorker(action: SagaActionFromCreator<typeof actions.fetchImage>) {
  const pointId = action.meta.arg

  // FETCH via GraphQL
  const result: { data: GetTrainingDataQuery } = yield call([client, client.query], {
    query: GET_TRAINING_DATA,
    variables: { id: pointId },
    fetchPolicy: 'network-only', // Ensure freshness
  })

  const pt = result.data.point

  if (!pt || !pt.imageUrl) {
    throw new Error('No image found for this point')
  }

  return {
    url: pt.imageUrl.startsWith('/') ? pt.imageUrl : `/${pt.imageUrl}`,
    manualRqi: pt.manualRqi || null,
    annotations: (pt.manualAnnotations || []) as Annotation[],
    tags: pt.manualTags || [],
    manualComment: pt.manualComment || '',
  }
}

function* fetchListWorker(action: SagaActionFromCreator<typeof actions.fetchList>) {
  const { mode, offset = 0, model = 'yolo' } = action.meta.arg

  const result: {
    data: { trainingPoints: { items: TrainingPoint[]; totalCount: number; hasMore: boolean } }
  } = yield call([client, client.query], {
    query: GET_TRAINING_POINTS,
    variables: { mode: mode.toUpperCase(), offset, limit: 20, model },
    fetchPolicy: 'network-only',
  })

  const { items, totalCount, hasMore } = result.data.trainingPoints

  return {
    items,
    totalCount,
    hasMore,
  }
}

function* fetchStatsWorker(action: SagaActionFromCreator<typeof actions.fetchStats>) {
  const { mode, model } = action.meta.arg
  const isDino = model === 'dino'

  const result: { data: { trainingStats: TrainingStats } } = yield call([client, client.query], {
    query: GET_TRAINING_STATS,
    variables: { mode: mode.toUpperCase(), isDino },
    fetchPolicy: 'network-only',
  })

  if (!result || !result.data) {
    throw new Error('Failed to fetch training stats: No data returned')
  }

  return result.data.trainingStats
}

function* saveAnnotationsWorker() {
  const state: ReturnType<typeof selectTrainingState> = yield select(selectTrainingState)

  const imageUrl = state.imageUrl
  let filename = ''
  if (imageUrl) {
    const parts = imageUrl.split('/')
    filename = parts[parts.length - 1]
  }

  if (!filename) {
    throw new Error('Cannot determine filename to save.')
  }

  const input = {
    imageFilename: filename,
    manualRqi: state.manualRqi,
    annotations: state.annotations,
    tags: state.tags,
    manualComment: state.manualComment,
    metaData: {
      agent: 'antigravity-web-client',
      timestamp: new Date().toISOString(),
    },
  }

  yield call([client, client.mutate], {
    mutation: SAVE_TRAINING_DATA,
    variables: { input },
  })

  return {
    rqi: state.manualRqi,
    tags: [...state.tags],
    comment: state.manualComment,
  }
}

function* deleteTrainingDataWorker(
  action: SagaActionFromCreator<typeof actions.deleteTrainingData>,
) {
  const filename = action.meta.arg

  yield call([client, client.mutate], {
    mutation: DELETE_TRAINING_DATA,
    variables: { imageFilename: filename },
  })
}

// ... imports ...
// Duplicates removed


// ... (keep fetch workers) ...

// Remove SSE polling logic completely

function* stopJobSaga(action: SagaActionFromCreator<typeof actions.stopJob>) {
  const jobId = action.meta.arg
  yield call([client, client.mutate], {
    mutation: STOP_JOB,
    variables: { jobId },
  })
  // No local state update needed, poller will reflect cancellation
}

// Restore active job state on reload
function* reconnectJobSaga() {
  const result: { data: GetActiveJobQuery } = yield call([client, client.query], {
    query: GET_ACTIVE_JOB,
    fetchPolicy: 'network-only',
  })

  if (result.data?.activeJob) {
    const job = result.data.activeJob

    // If backend reports job as completed, do NOT show it on UI upon reconnect/reload.
    if (job.status.toLowerCase() === 'completed' || (job.total > 0 && job.progress >= job.total)) {
      // yield put(actions.setAnalysisStatus('idle')) // Removed
      return
    }

    // Register generic job
    yield put(apiActions.registerJob(job.id))
    
    // Update local state with the found Job ID
    yield put(actions.setAnalysisJobId(job.id))
  }
}

function* runAnalysisSaga(action: SagaActionFromCreator<typeof actions.runAnalysis>) {
  const input = action.meta.arg
  const result: { data: { runAnalysis: { id: string } } } = yield call([client, client.mutate], {
    mutation: RUN_ANALYSIS,
    variables: { input },
  })

  const jobId = result.data.runAnalysis.id
  yield put(apiActions.registerJob(jobId))
  return { jobId }
}

function* startTrainingSaga() {
  const result: { data: { startModelTraining: { id: string } } } = yield call(
    [client, client.mutate],
    {
      mutation: START_MODEL_TRAINING,
    },
  )

  const jobId = result.data.startModelTraining.id
  yield put(apiActions.registerJob(jobId))
  return { jobId }
}

const PERFORM_REVIEW_ACTION = gql(`
    mutation PerformReviewAction($input: ReviewActionInput!) {
        performReviewAction(input: $input) {
            success
            message
            processedImageUrl
            annotations {
                id
                label
                score
                type
                points
            }
        }
    }
`)

function* reviewActionWorker(action: SagaActionFromCreator<typeof actions.performReviewAction>) {
  const { actionType, params } = action.meta.arg
  const state: ReturnType<typeof selectTrainingState> = yield select(selectTrainingState)
  
  // Ensure we have a filename
  const filename = state.imageUrl?.split('/').pop()
  const finalParams = { ...params }
  
  if (!finalParams.filename && filename) {
      finalParams.filename = filename
  }

  const result: { data: { performReviewAction: ReviewActionResult } } = yield call([client, client.mutate], {
    mutation: PERFORM_REVIEW_ACTION,
    variables: {
      input: {
        actionType,
        parameters: finalParams,
      },
    },
  })

  const response = result.data.performReviewAction
  
  if (!response.success) {
      throw new Error(response.message || 'Review action failed')
  }

  return {
      annotations: response.annotations,
      processedImageUrl: response.processedImageUrl,
      message: response.message
  }
}

export default [
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  takeLatestAsync((fetchImage as any).type || fetchImage, fetchImageWorker),
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  takeLatestAsync((fetchList as any).type || fetchList, fetchListWorker),
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  takeLatestAsync((fetchStats as any).type || fetchStats, fetchStatsWorker),
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  takeLatestAsync((actions.saveAnnotations as any).type || actions.saveAnnotations, saveAnnotationsWorker),
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  takeLatestAsync((actions.deleteTrainingData as any).type || actions.deleteTrainingData, deleteTrainingDataWorker),
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  takeLatestAsync((actions.performReviewAction as any).type || actions.performReviewAction, reviewActionWorker),
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  takeLatestAsync((actions.runAnalysis as any).type || actions.runAnalysis, runAnalysisSaga),
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  takeLatestAsync((actions.startTraining as any).type || actions.startTraining, startTrainingSaga),
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  takeLatestAsync((actions.stopJob as any).type || actions.stopJob, stopJobSaga),
  takeLatest(actions.reconnectJob.type, reconnectJobSaga),
]
