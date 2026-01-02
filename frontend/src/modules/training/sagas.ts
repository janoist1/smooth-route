import { call, select, put, fork, takeLatest, take } from 'redux-saga/effects'
import { eventChannel, END } from 'redux-saga'

import { actions, fetchImage, fetchList, fetchStats } from './slice'

import { takeLatestAsync } from 'saga-toolkit'
import { client, gql } from '../graphql'
import type { GetTrainingDataQuery } from '../graphql/generated/graphql'
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
            jobId
        }
    }
`)

const START_MODEL_TRAINING = gql(`
    mutation StartModelTraining {
        startModelTraining {
            jobId
        }
    }
`)

// Logic to fetch image from API
// eslint-disable-next-line @typescript-eslint/no-explicit-any
function* fetchImageWorker(action: any) {
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
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    annotations: (pt.manualAnnotations || []) as any[],
    tags: pt.manualTags || [],
    manualComment: pt.manualComment || '',
  }
}

import type { FilterMode } from '../graphql/generated/graphql'

function* fetchListWorker(action: { meta: { arg: { mode: FilterMode; offset?: number } } }) {
  const { mode, offset = 0 } = action.meta.arg

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const result: { data: { trainingPoints: any } } = yield call([client, client.query], {
    query: GET_TRAINING_POINTS,
    variables: { mode, offset, limit: 100 },
    fetchPolicy: 'network-only',
  })

  const { items, totalCount, hasMore } = result.data.trainingPoints

  return {
    items,
    totalCount,
    hasMore
  }
}

function* fetchStatsWorker(action: { meta: { arg: { mode: FilterMode } } }) {
  const { mode } = action.meta.arg

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const result: { data: { trainingStats: any } } = yield call([client, client.query], {
    query: GET_TRAINING_STATS,
    variables: { mode },
    fetchPolicy: 'network-only',
  })

  if (!result || !result.data) {
    throw new Error('Failed to fetch training stats: No data returned')
  }

  return result.data.trainingStats
}

function* saveAnnotationsWorker() {
  try {
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
  } catch (error) {
    console.error('Failed to save training data:', error)
    throw error // This triggers .rejected
  }
}

function createJobChannel(jobId: string) {
  return eventChannel(emitter => {
    const eventSource = new EventSource(`/api/v1/job/${jobId}/stream`)

    eventSource.onmessage = event => {
      try {
        const data = JSON.parse(event.data)
        emitter(data)
        
        if (data.status === 'completed' || data.status === 'failed') {
          emitter(END)
        }
      } catch (err) {
        console.error('Failed to parse SSE data:', err)
        emitter(END)
      }
    }

    eventSource.onerror = error => {
      console.error('SSE Error:', error)
      emitter(END)
    }

    return () => {
      eventSource.close()
    }
  })
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
function* pollAnalysisJobWorker(jobId: string): Generator<any, void, any> {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const channel: any = yield call(createJobChannel, jobId)
  try {
    while (true) {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const job: any = yield take(channel)
      
      yield put(actions.updateJobProgress({
        progress: job.progress,
        total: job.total,
        message: job.message,
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        status: job.status.toLowerCase() as any
      }))
    }
  } catch (error) {
    console.error('Job channel error:', error)
  } finally {
    if (channel && channel.close) channel.close()
    
    // Safety check: if we finished but are still in 'running' state, 
    // it means the channel closed unexpectedly (e.g. network error)
    // without a final status update. Let's do one last poll to be sure.
    const state: ReturnType<typeof selectTrainingState> = yield select(selectTrainingState)
    if (state.analysisStatus === 'running') {
      try {
        const response: Response = yield call(fetch, `/api/v1/job/${jobId}`)
        if (response.ok) {
          const job = yield call([response, response.json])
          yield put(actions.updateJobProgress({
            progress: job.progress,
            total: job.total,
            message: job.message,
            status: job.status.toLowerCase()
          }))
        } else {
          yield put(actions.setAnalysisStatus('idle'))
        }
      } catch (err) {
        console.error('Final job status poll failed:', err)
        yield put(actions.setAnalysisStatus('idle'))
      }
    }
  }
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
function* stopJobSaga(): Generator<any, void, any> {
  try {
    const state: ReturnType<typeof selectTrainingState> = yield select(selectTrainingState)
    const jobId = state.analysisJobId
    
    if (jobId) {
      yield call(fetch, `/api/v1/job/${jobId}/stop`, { method: 'POST' })
      yield put(actions.updateJobProgress({
        progress: 0,
        total: 0,
        message: 'Folyamat leállítva.',
        status: 'cancelled'
      }))
    }
  } catch (error) {
    console.error('Failed to stop job:', error)
  }
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
function* reconnectJobSaga(): Generator<any, void, any> {
  try {
    const response: Response = yield call(fetch, '/api/v1/jobs/active')
    const { job } = yield call([response, response.json])
    
    if (job && (job.status === 'running' || job.status === 'pending')) {
      yield put(actions.updateJobProgress({
        progress: job.progress,
        total: job.total,
        message: job.message,
        // Ensure we don't pass 'pending' to frontend which expects idle/running
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        status: (job.status === 'pending' ? 'running' : job.status) as any
      }))
      yield put(actions.runAnalysisSuccess({ jobId: job.job_id }))
      yield fork(pollAnalysisJobWorker, job.job_id)
    } else {
      // No active job, ensure we aren't showing a stale loading state
      const state: ReturnType<typeof selectTrainingState> = yield select(selectTrainingState)
      if (state.analysisStatus === 'running') {
        yield put(actions.setAnalysisStatus('idle'))
      }
    }
  } catch (error) {
    console.error('Failed to reconnect to active job:', error)
  }
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
function* runAnalysisSaga(action: any): Generator<any, void, any> {
  try {
    const input = action.payload
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const result: { data: any } = yield call([client, client.mutate], {
      mutation: RUN_ANALYSIS,
      variables: { input },
    })
    
    const jobId = result.data.runAnalysis.jobId
    yield put(actions.runAnalysisSuccess({ jobId }))
    yield fork(pollAnalysisJobWorker, jobId)
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
  } catch (error: any) {
    yield put(actions.runAnalysisFailure(error.message))
  }
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
function* startTrainingSaga(): Generator<any, void, any> {
  try {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const result: { data: any } = yield call([client, client.mutate], {
      mutation: START_MODEL_TRAINING,
    })
    
    const jobId = result.data.startModelTraining.jobId
    yield put(actions.startTrainingSuccess({ jobId }))
    yield fork(pollAnalysisJobWorker, jobId)
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
  } catch (error: any) {
    yield put(actions.startTrainingFailure(error.message))
  }
}

export default [
  takeLatestAsync(fetchImage.type, fetchImageWorker),
  takeLatestAsync(fetchList.type, fetchListWorker),
  takeLatestAsync(fetchStats.type, fetchStatsWorker),
  takeLatestAsync(actions.saveAnnotations.type, saveAnnotationsWorker),
  takeLatest(actions.runAnalysis.type, runAnalysisSaga),
  takeLatest(actions.startTraining.type, startTrainingSaga),
  takeLatest(actions.stopJob.type, stopJobSaga),
  takeLatest('training/reconnectJob', reconnectJobSaga),
]
