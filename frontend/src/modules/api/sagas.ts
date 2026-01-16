
import { call, put, take } from 'redux-saga/effects'
import { eventChannel, END } from 'redux-saga'
import { SagaActionFromCreator, takeLatestAsync } from 'saga-toolkit'
import { actions } from './slice'
import { client, gql } from '../graphql'
import { takeEvery, cancelled } from 'redux-saga/effects'

const GET_JOB = gql(`
  query GetJob($id: String!) {
    job(id: $id) {
      id
      status
      progress
      total
      message
      result
      error
      created
      started
      completed
    }
  }
`)

function* pollJobWorker(action: SagaActionFromCreator<typeof actions.pollJob>) {
    const jobId = action.meta.arg
    
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const result: { data: any } = yield call([client, client.query], {
        query: GET_JOB,
        variables: { id: jobId },
        fetchPolicy: 'network-only'
    })
    
    const job = result.data.job
    if (!job) throw new Error(`Job ${jobId} not found`)
    
    return {
        id: job.id,
        status: job.status,
        progress: job.progress || 0,
        total: job.total || 100,
        message: job.message,
        error: job.error,
        result: job.result
    }
}

// SSE Channel Factory
function createJobChannel(jobId: string) {
  return eventChannel(emit => {
    console.log(`[API] Opening SSE connection for job ${jobId}`)
    const es = new EventSource(`http://localhost:8000/api/v1/job/${jobId}/stream`)

    es.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data)
        emit(data)
        
        // Auto-close on terminal states
        if (['completed', 'failed', 'cancelled'].includes(data.status?.toLowerCase())) {
           emit(END)
        }
      } catch (err) {
        console.error('SSE Parse Error', err)
      }
    }

    es.onerror = (error) => {
      console.error('SSE Error', error)
      if (es.readyState === 2) {
          emit(END)
      }
    }

    return () => {
      console.log(`[API] Closing SSE connection for job ${jobId}`)
      es.close()
    }
  })
}


function* watchRegisterJob(action: ReturnType<typeof actions.registerJob>) {
    const jobId = action.payload
    yield call(sseJobWorker, jobId)
}

function* sseJobWorker(jobId: string) {
    let channel
    try {
        channel = yield call(createJobChannel, jobId)
        
        while (true) {
            // eslint-disable-next-line @typescript-eslint/no-explicit-any
            const data: any = yield take(channel as any)
            
            // Map SSE data to store format
            // Backend sends: { job_id, status, progress, total, message, ... }
            yield put(actions.updateJob({
                id: jobId,
                status: data.status,
                progress: data.progress,
                total: data.total,
                message: data.message,
                result: data.result,
                error: data.error
            }))
        }
    } catch (err) {
        console.error('SSE Saga Error', err)
    } finally {
        if (yield cancelled()) {
             if (channel) channel.close()
        }
    }
}

export default [
    takeLatestAsync(actions.pollJob.type, pollJobWorker),
    takeEvery(actions.registerJob.type, watchRegisterJob),
]
