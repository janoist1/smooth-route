
import { call, put, take, cancelled, fork, cancel } from 'redux-saga/effects'
import type { Task, EventChannel, SagaIterator } from 'redux-saga'
import { eventChannel, END } from 'redux-saga'
import { type SagaActionFromCreator, takeLatestAsync } from 'saga-toolkit'
import { actions } from './slice'
import { client, gql } from '../graphql'

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
      createdAt
      completedAt
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
        result: job.result,
        startedAt: job.createdAt,
        completedAt: job.completedAt,
    }
}

// SSE Channel Factory
function createJobChannel(jobId: string) {
  return eventChannel(emit => {
    console.log(`[API] Opening SSE connection for job ${jobId}`)
    const es = new EventSource(`/api/v1/job/${jobId}/stream`)

    es.onerror = (error) => {
      console.error('SSE Error', error)
      if (es.readyState === 2) {
          emit(END)
      }
    }

    es.addEventListener('error', (e: Event) => {
        // Backend sends yield {"event": "error", "data": "Job not found"}
        // Casting e to any to access data if it exists, or just log
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        console.error("SSE Custom Error Event:", (e as any).data)
        emit(END) 
        es.close()
    })

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

    return () => {
      console.log(`[API] Closing SSE connection for job ${jobId}`)
      es.close()
    }
  })
}

interface JobEventData {
  job_id: string
  status: 'pending' | 'running' | 'completed' | 'failed' | 'cancelled' | 'unknown'
  progress: number
  total: number
  message: string
  result?: unknown
  error?: string | null
}

// Fixed Sagas with correct typing

function* sseJobWorker(jobId: string): SagaIterator {
    let channel: EventChannel<JobEventData> | undefined
    try {
        channel = (yield call(createJobChannel, jobId)) as EventChannel<JobEventData>
        
        while (true) {
            const data: JobEventData = yield take(channel)
            
            // Map SSE data to store format
            yield put(actions.updateJob({
                id: jobId,
                status: data.status,
                progress: data.progress,
                total: data.total,
                message: data.message,
                result: data.result,
                error: data.error || null
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

// Replaces takeEvery/takeLatest with a specific deduplication logic per Job ID
function* watchRegisterJob(): SagaIterator {
    const tasks: Record<string, Task> = {}

    while (true) {
        const action: ReturnType<typeof actions.registerJob> = yield take(actions.registerJob.type)
        const jobId = action.payload

        // If we are already monitoring this job, cancel the old worker to allow restart/refresh
        if (tasks[jobId]) {
            yield cancel(tasks[jobId])
        }

        // Start new worker
        tasks[jobId] = yield fork(sseJobWorker, jobId)
    }
}

export default [
    takeLatestAsync(actions.pollJob.type, pollJobWorker),
    fork(watchRegisterJob),
]
