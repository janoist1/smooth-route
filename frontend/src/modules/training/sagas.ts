import { call, select, put, fork, take, cancelled, takeLatest } from 'redux-saga/effects'
import { eventChannel, END } from 'redux-saga'

import { actions, fetchImage, fetchList, fetchStats } from './slice'
import type { TrainingState, Annotation, TrainingPoint, TrainingStats } from './types'

import { takeLatestAsync } from 'saga-toolkit'
import type { SagaActionFromCreator } from 'saga-toolkit'
import { client, gql } from '../graphql'
import type { GetTrainingDataQuery, GetJobQuery, GetActiveJobQuery, DetectObjectsMutation } from '../graphql/generated/graphql'
import { selectTrainingState } from './selectors'

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

const GET_JOB = gql(`
    query GetJob($id: String!) {
        job(id: $id) {
            id
            type
            status
            progress
            total
            details
            result
            createdAt
            completedAt
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

  const result: { data: { trainingPoints: { items: TrainingPoint[]; totalCount: number; hasMore: boolean } } } = yield call([client, client.query], {
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

// Poll job status via Server-Sent Events (SSE)
function createJobChannel(jobId: string) {
  return eventChannel<{
    progress: number
    total: number
    message: string
    status: string
    details?: string
  }>(emitter => {
    const eventSource = new EventSource(`/api/v1/job/${jobId}/stream`)

    eventSource.onmessage = event => {
      try {
        const data = JSON.parse(event.data)
        emitter(data)

        if (data.status === 'completed' || data.status === 'failed' || data.status === 'cancelled') {
          emitter(END)
        }
      } catch {
        // Silent fail on parse error
      }
    }

    eventSource.onerror = () => {
      eventSource.close()
      emitter(END)
    }

    return () => {
      eventSource.close()
    }
  })
}

// Worker to poll job status and update state
function* pollAnalysisJobWorker(jobId: string) {
  const channel: ReturnType<typeof createJobChannel> = yield call(createJobChannel, jobId)
  
  try {
    while (true) {
      const job: {
        progress: number
        total: number
        message: string
        status: string
      } = yield take(channel)

      yield put(
        actions.updateJobProgress({
          progress: job.progress,
          total: job.total,
          message: job.message,
          // Use generic 'running' status map if needed, or cast to known types
          status: job.status.toLowerCase() as TrainingState['analysisStatus'],
        }),
      )

      if (job.status.toLowerCase() === 'completed' || 
          job.status.toLowerCase() === 'failed' || 
          job.status.toLowerCase() === 'cancelled' ||
          (job.total > 0 && job.progress >= job.total)) {
        break
      }
    }
  } catch {
    // Channel error
  } finally {
    const isCancelled: boolean = yield cancelled()
    if (isCancelled) {
      // If cancelled (e.g. by new reconnect or navigation), close channel but DO NOT trigger completion.
      // This prevents race conditions where an old cancelled poller overwrites the state.
      if (channel) {
        channel.close()
      }
    } else {
      // Normal completion (break from loop)
      if (channel) {
        channel.close()
      }
      // Check final status from API to ensure we didn't miss the last update (especially exports)
      yield call(checkFinalJobStatus, jobId)
    }
  }
}

// Helper to check final status via REST API
function* checkFinalJobStatus(jobId: string) {
  try {
      const finalResult: { data: GetJobQuery } = yield call([client, client.query], {
        query: GET_JOB,
        variables: { id: jobId },
        fetchPolicy: 'network-only',
      })

      const job = finalResult.data.job
      if (job) {
        if (job.status === 'failed') {
          const errorMsg = job.details 
            ? (JSON.parse(job.details).error || 'Unknown error') 
            : 'Unknown error'
          yield put(actions.jobFailed(errorMsg))
        } else if (job.status === 'completed' || (job.total > 0 && job.progress >= job.total)) {
          // Extract exports from job result
          const jobResult = job.result ? (typeof job.result === 'string' ? JSON.parse(job.result) : job.result) : null
          
          let exports = null
          if (jobResult?.exports) {
            exports = {
              notebookPath: jobResult.exports.notebook_path || jobResult.exports.notebookPath,
              datasetPath: jobResult.exports.dataset_path || jobResult.exports.datasetPath,
              instructions: jobResult.instructions,
            }
          }

          yield put(actions.jobCompleted({ exports }))
          // Refresh data
          yield put(actions.fetchStats({ mode: 'ALL' }))
          yield put(actions.fetchList({ mode: 'ALL' }))
        } else if (job.status === 'cancelled') {
             // Ensure status is cancelled and message is preserved (or updated)
             const msg = job.details 
                ? (JSON.parse(job.details).message || 'Folyamat leállítva.') 
                : 'Folyamat leállítva.'
             yield put(actions.updateJobProgress({
               progress: job.progress,
               total: job.total,
               message: msg,
               status: 'cancelled'
             }))
        } else {
             // Still running? Maybe just network blip. 
             yield put(actions.setAnalysisStatus('idle'))
        }
      }
  } catch {
      yield put(actions.setAnalysisStatus('idle'))
  }
}

function* stopJobSaga(action: SagaActionFromCreator<typeof actions.stopJob>) {
  const jobId = action.meta.arg
  yield call([client, client.mutate], {
    mutation: STOP_JOB,
    variables: { jobId },
  })
  
  // Handled by polling, but we can optimistically update
  yield put(
    actions.updateJobProgress({
      progress: 0,
      total: 0,
      message: 'Folyamat leállítva.',
      status: 'cancelled',
    }),
  )
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
    // User expectation: "Fresh start" when entering the page, unless a job is actively running.
    // We ignore the completed job result here, leaving the state as 'idle' (or resetting it).
    if (job.status.toLowerCase() === 'completed' || (job.total > 0 && job.progress >= job.total)) {
        yield put(actions.setAnalysisStatus('idle'))
        return
    }
    
    // Restore state manually since this is a "re-" connection, not a fresh start
    // We use inner actions for this part as it doesn't fit the Request/Response cleanly
    
    // BUT we need to start the poller.
    yield put(
      actions.updateJobProgress({
        progress: job.progress,
        total: job.total,
        message: job.details ? JSON.parse(job.details).message || '' : '',
        status: job.status as TrainingState['analysisStatus'],
      }),
    )
    yield call(pollAnalysisJobWorker, job.id)
  } else {
    // No active job
    const state: ReturnType<typeof selectTrainingState> = yield select(selectTrainingState)
    if (state.analysisStatus === 'running') {
      yield put(actions.setAnalysisStatus('idle'))
    }
  }
}

function* runAnalysisSaga(action: SagaActionFromCreator<typeof actions.runAnalysis>) {
  const input = action.meta.arg
  const result: { data: { runAnalysis: { id: string } } } = yield call([client, client.mutate], {
    mutation: RUN_ANALYSIS,
    variables: { input },
  })

  const jobId = result.data.runAnalysis.id
  yield fork(pollAnalysisJobWorker, jobId)
  return { jobId }
}

function* startTrainingSaga() {
  const result: { data: { startModelTraining: { id: string } } } = yield call([client, client.mutate], {
    mutation: START_MODEL_TRAINING,
  })

  const jobId = result.data.startModelTraining.id
  yield fork(pollAnalysisJobWorker, jobId)
  return { jobId }
}

function* autoDetectWorker(action: SagaActionFromCreator<typeof actions.autoDetect>) {
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
    const annotations = predictions.map((p) => ({
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
