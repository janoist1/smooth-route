
import { createSlice, type PayloadAction } from '@reduxjs/toolkit'
import { createSagaAction } from 'saga-toolkit'
import type { RootState } from '../../store'

export interface JobState {
    id: string
    status: 'pending' | 'running' | 'completed' | 'failed' | 'cancelled' | 'unknown'
    progress: number
    total: number
    message: string | null
    error: string | null
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    result: any
    startedAt?: string
    completedAt?: string
    step?: string
}

export interface JobsState {
    jobs: Record<string, JobState>
    activeJobId: string | null // Global active job if any
}

const initialState: JobsState = {
    jobs: {},
    activeJobId: null
}

export const pollJob = createSagaAction<string, JobState>('api/pollJob')
export const stopJob = createSagaAction<string, void>('api/stopJob')

const apiSlice = createSlice({
    name: 'api',
    initialState,
    reducers: {
        registerJob(state, action: PayloadAction<string>) {
            // Initialize a placeholder for a job we just started
            state.jobs[action.payload] = {
                id: action.payload,
                status: 'pending',
                progress: 0,
                total: 0,
                message: 'Initializing...',
                error: null,
                result: null
            }
            state.activeJobId = action.payload
        },
        updateJob(state, action: PayloadAction<JobState>) {
            state.jobs[action.payload.id] = action.payload
            // If this update matches active job, no extra action needed, it just updates
            if (['completed', 'failed', 'cancelled'].includes(action.payload.status.toLowerCase())) {
                 if (state.activeJobId === action.payload.id) {
                     // Optionally keep it active to show final status, or clear it?
                     // Usually better to keep it so UI can show "Done"
                 }
            }
        },
        clearActiveJob(state) {
            state.activeJobId = null
        }
    },
    extraReducers: (builder) => {
        builder.addCase(pollJob.fulfilled, (state, action) => {
            state.jobs[action.payload.id] = action.payload
        })
    }
})

export const actions = { ...apiSlice.actions, pollJob, stopJob }
export default apiSlice.reducer

// Selectors
export const selectJob = (state: RootState, jobId: string | null) => 
    jobId ? state.api.jobs[jobId] : null

export const selectActiveJob = (state: RootState) => 
    state.api.activeJobId ? state.api.jobs[state.api.activeJobId] : null
