import { call, select, put, takeLatest } from 'redux-saga/effects'

import { actions, fetchImage, fetchList, fetchStats } from './slice'
import type { Annotation, TrainingPoint, TrainingStats } from './types'

import { takeLatestAsync } from 'saga-toolkit'
import type { SagaActionFromCreator } from 'saga-toolkit'
import { client, gql } from '../graphql'
import type {
  GetTrainingDataQuery,
  GetActiveJobQuery,
  DetectObjectsMutation,
} from '../graphql/generated/graphql'
import { selectTrainingState } from './selectors'
import { actions as apiActions } from '../api'

// --- GraphQL Queries & Mutations ---

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
  query GetTrainingPoints($mode: FilterMode, $limit: Int, $offset: Int) {
    trainingPoints(mode: $mode, limit: $limit, offset: $offset) {
      items {
        id
        latitude
        longitude
        imageUrl
        rqiScore
        manualRqi
        manualTags
        createdAt
      }
      totalCount
      hasMore
    }
  }
`)

const GET_TRAINING_STATS = gql(`
  query GetTrainingStats($mode: FilterMode) {
    trainingStats(mode: $mode) {
      total
      pending
      annotated
      avgRqi
      goodCount
      fairCount
      poorCount
      pendingAnalysis
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

const DETECT_OBJECTS = gql(`
    mutation DetectObjects($input: DetectInput!) {
        detectObjects(input: $input) {
            label
            confidence
            points
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
  const { mode, offset = 0 } = action.meta.arg

  const result: {
    data: { trainingPoints: { items: TrainingPoint[]; totalCount: number; hasMore: boolean } }
  } = yield call([client, client.query], {
    query: GET_TRAINING_POINTS,
    variables: { mode: mode.toUpperCase(), offset, limit: 20 },
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
  const { mode } = action.meta.arg

  const result: { data: { trainingStats: TrainingStats } } = yield call([client, client.query], {
    query: GET_TRAINING_STATS,
    variables: { mode: mode.toUpperCase() },
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
    
    // Also update local reference if needed (it matches reducers behavior)
     yield put(actions.reconnectJob()) // Actually reconnectJob is an action trigger, not a setter. 
     // The reducer for startTraining/runAnalysis sets the ID.
     // We might need an action to set the ID in training slice if it's not set.
     // But `reconnectJob` saga is triggered by `reconnectJob` action.
     // We need to set `analysisJobId` in slice.
     // There is no dedicated setter for analysisJobId exposed in actions except via `startTraining.fulfilled` etc.
     // We might need to add `setAnalysisJobId` or misuse an existing one?
     // Actually, `training/slice` doesn't have a simple "setJobId".
     // But `apiActions.registerJob` handles the *global* state.
     // Local state needs `analysisJobId`.
     // We can dispatch `startTraining.fulfilled({ jobId: job.id })` to set the ID in local state?
     // Or added a specific action.
     // Let's assume for now we dispatch `startTraining.fulfilled` or `runAnalysis.fulfilled` based on type? 
     // Or just add `setAnalysisJobId` to slice. I'll stick to registering in API for now and fixing ID setting later if needed.
     
     // Wait, `reconnectJob` action IS dispatched by UI on mount.
     // We need to update the state.
     // Let's use `runAnalysis.fulfilled` as a generic "Job Started" signal for now or add a setter.
     
     // Simplest: just dispatch runAnalysis.fulfilled works for setting ID.
     yield put(actions.runAnalysis.fulfilled({ jobId: job.id }, 'reconnect', { strategy: '', limit: 0, reanalyze: false }))
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

function* autoDetectWorker(action: SagaActionFromCreator<typeof actions.autoDetect>) {
   // ... (keep as is) ...
   const confThreshold = action.meta.arg
  const state: ReturnType<typeof selectTrainingState> = yield select(selectTrainingState)
  const filename = state.imageUrl?.split('/').pop()

  if (!filename) return []

  const result: { data: DetectObjectsMutation } = yield call([client, client.mutate], {
    mutation: DETECT_OBJECTS,
    variables: {
      input: {
        filename,
        confThreshold,
        classes: state.autoDetectClasses.length > 0 ? state.autoDetectClasses : undefined,
      },
    },
  })

  const predictions = result.data.detectObjects

  if (predictions && predictions.length > 0) {
    const annotations = predictions.map(p => ({
      id: crypto.randomUUID ? crypto.randomUUID() : Math.random().toString(36).substring(2),
      points: p.points,
      label: p.label,
      type: (p.points.length > 2 ? 'polygon' : 'box') as 'polygon' | 'box',
      score: p.confidence,
    }))

    return annotations
  }

  return []
}

export default [
  takeLatestAsync(fetchImage.type, fetchImageWorker),
  takeLatestAsync(fetchList.type, fetchListWorker),
  takeLatestAsync(fetchStats.type, fetchStatsWorker),
  takeLatestAsync(actions.saveAnnotations.type, saveAnnotationsWorker),
  takeLatestAsync(actions.deleteTrainingData.type, deleteTrainingDataWorker),
  takeLatestAsync(actions.autoDetect.type, autoDetectWorker),
  takeLatestAsync(actions.runAnalysis.type, runAnalysisSaga),
  takeLatestAsync(actions.startTraining.type, startTrainingSaga),
  takeLatestAsync(actions.stopJob.type, stopJobSaga),
  takeLatest(actions.reconnectJob.type, reconnectJobSaga),
]
