import { createSlice, PayloadAction, AnyAction, createAction } from '@reduxjs/toolkit'
import { createSagaAction } from 'saga-toolkit'
import type { TrainingState, Annotation, TrainingPoint, TrainingStats, DamageLabel } from './types'
import { filterAnnotationsNMS } from './utils'

// Actions
interface FetchImageSuccess {
  url: string
  manualRqi: number | null
  tags: string[]
  annotations: Annotation[]
  manualComment: string | null
}

interface FetchListSuccess {
  items: TrainingPoint[]
  totalCount: number
  hasMore: boolean
}

export const fetchImage = createSagaAction<number, FetchImageSuccess>('training/fetchImage')
export const fetchList = createSagaAction<{ mode: string; offset?: number }, FetchListSuccess>(
  'training/fetchList',
)
export const fetchStats = createSagaAction<{ mode: string }, TrainingStats>('training/fetchStats')
export const saveAnnotations = createSagaAction<
  void,
  { rqi: number | null; tags: string[]; comment: string }
>('training/saveAnnotations')
export const deleteTrainingData = createSagaAction<string, void>('training/deleteTrainingData')

export const autoDetect = createSagaAction<number | undefined, Annotation[]>('training/autoDetect')

// Job Actions
// Job Actions
export const reconnectJob = createAction('training/reconnectJob')
export const runAnalysis = createSagaAction<
  { strategy: string; limit: number; reanalyze: boolean },
  { jobId: string }
>('training/runAnalysis')
export const startTraining = createSagaAction<void, { jobId: string }>('training/startTraining')
export const stopJob = createSagaAction<string, void>('training/stopJob')

const initialState: TrainingState = {
  imageId: null,
  imageUrl: null,
  annotations: [],
  loading: false,
  saving: false,
  error: null,
  brushSize: 20,
  selectedTool: 'pothole',
  manualRqi: null,
  tags: [],
  manualComment: '',
  lastSavedSettings: null,

  // Job Tracking
  analysisJobId: null,
  analysisProgress: 0,
  analysisTotal: 0,
  analysisStatus: 'idle',
  analysisMessage: '',
  trainingStatus: 'idle',
  navigationIds: [],
  items: [],

  // Pagination & Stats
  totalCount: 0,
  hasMore: false,
  offset: 0,
  activeMode: 'all',
  globalStats: null,
  autoDetectConf: 0.25,
  autoDetectClasses: [],
}

const trainingSlice = createSlice({
  name: 'training',
  initialState,
  reducers: {
    setAutoDetectClasses(state, action: PayloadAction<string[]>) {
      state.autoDetectClasses = action.payload
    },
    // Lifecycle
    unmount(state) {
      state.imageId = null
      state.imageUrl = null
      state.annotations = []
      state.tags = []
      state.manualRqi = null
      state.manualComment = ''
      state.error = null
      state.loading = false
      state.lastSavedSettings = null
      state.exports = null
    },

    // Annotation Actions
    addAnnotation(state, action: PayloadAction<Annotation>) {
      state.annotations.push(action.payload)
    },
    setAutoDetections(state, action: PayloadAction<Annotation[]>) {
      state.annotations.push(...action.payload)
    },
    removeAnnotation(state, action: PayloadAction<string>) {
      state.annotations = state.annotations.filter(a => a.id !== action.payload)
    },
    updateAnnotation(state, action: PayloadAction<Annotation>) {
      const index = state.annotations.findIndex(a => a.id === action.payload.id)
      if (index !== -1) {
        state.annotations[index] = action.payload
      }
    },
    setTool(state, action: PayloadAction<DamageLabel>) {
      state.selectedTool = action.payload
    },
    setRqi(state, action: PayloadAction<number>) {
      state.manualRqi = action.payload
    },
    addTag(state, action: PayloadAction<string>) {
      if (!state.tags.includes(action.payload)) {
        state.tags.push(action.payload)
      }
    },
    removeTag(state, action: PayloadAction<string>) {
      state.tags = state.tags.filter(t => t !== action.payload)
    },
    setComment(state, action: PayloadAction<string>) {
      state.manualComment = action.payload
    },
    setSettings(
      state,
      action: PayloadAction<{ rqi: number | null; tags: string[]; comment: string }>,
    ) {
      if (action.payload.rqi !== undefined) state.manualRqi = action.payload.rqi
      if (action.payload.tags !== undefined) state.tags = action.payload.tags
      if (action.payload.comment !== undefined) state.manualComment = action.payload.comment
    },
    updateJobProgress(
      state,
      action: PayloadAction<{
        progress: number
        total: number
        message: string
        status?: TrainingState['analysisStatus']
      }>,
    ) {
      state.analysisProgress = action.payload.progress
      state.analysisTotal = action.payload.total
      state.analysisMessage = action.payload.message
      if (action.payload.status) {
        // Enforce state machine constraint: Once 'completed' or 'failed', cannot go back to 'running' for the SAME flow.
        // This handles race conditions where a lagging poller sends old status updates.
        if (state.analysisStatus === 'completed' && action.payload.status !== 'completed') {
           // Ignore
        } else {
           state.analysisStatus = action.payload.status
        }
      }
      
      // Auto-complete if 100% processed
      const isFinished = action.payload.total > 0 && action.payload.progress >= action.payload.total
      if (isFinished && state.analysisStatus !== 'failed') {
          state.analysisStatus = 'completed'
      }
    },
    setAnalysisStatus(state, action: PayloadAction<TrainingState['analysisStatus']>) {
      state.analysisStatus = action.payload
    },
    setAutoDetectConf(state, action: PayloadAction<number>) {
      state.autoDetectConf = action.payload
    },
    // Filters current annotations using NMS with given threshold
    filterCurrentAnnotations(state, action: PayloadAction<number>) {
      const threshold = action.payload
      if (!state.annotations || state.annotations.length === 0) return
      
      const filtered = filterAnnotationsNMS(state.annotations, threshold)
      state.annotations = filtered
    },
    
    // Manual Job State Updates (if needed for SSE)
    jobCompleted(state, action: PayloadAction<{ exports?: TrainingState['exports'] } | undefined>) {
      state.analysisStatus = 'completed'
      state.trainingStatus = 'completed' 
      state.analysisMessage = 'Kész!'
      state.analysisJobId = null
      state.exports = action.payload?.exports || null
    },
    jobFailed(state, action: PayloadAction<string>) {
      state.analysisStatus = 'failed'
      state.analysisMessage = action.payload
      state.trainingStatus = 'failed'
      state.exports = null
    },
    resetAnalysisJob(state) {
      state.analysisJobId = null
      state.analysisStatus = 'idle'
      state.analysisMessage = ''
      state.analysisProgress = 0
      state.analysisTotal = 0
      state.exports = null
    },
  },
  extraReducers: builder => {
    builder
      .addCase(autoDetect.pending, state => {
        state.loading = true
      })
      .addCase(autoDetect.fulfilled, (state, action: PayloadAction<Annotation[]>) => {
        state.loading = false
        state.annotations.push(...action.payload)
      })
      .addCase(autoDetect.rejected, (state, action: AnyAction) => {
        state.loading = false
        state.error = action.error.message || 'Auto-detect failed'
      })
      .addCase(fetchImage.pending, (state, action) => {
        // Safe access to meta.arg via types
        const payloadAction = action as unknown as PayloadAction<undefined, string, { arg: number }>
        const newId = payloadAction.meta.arg.toString()
        if (state.imageId !== newId) {
          state.imageId = newId
          state.imageUrl = null
          state.annotations = []
          state.manualRqi = null
          state.tags = []
          state.manualComment = ''
        }
        state.loading = true
        state.error = null
      })
      .addCase(saveAnnotations.pending, state => {
        state.saving = true
        state.error = null
        state.lastSavedSettings = {
          rqi: state.manualRqi,
          tags: [...state.tags],
          comment: state.manualComment,
        }
      })
      .addCase(saveAnnotations.fulfilled, (state, action: PayloadAction<{ rqi: number | null; tags: string[]; comment: string }>) => {
        state.saving = false
        if (action.payload) {
          state.lastSavedSettings = {
            rqi: action.payload.rqi,
            tags: [...action.payload.tags],
            comment: action.payload.comment,
          }
        }
      })
      .addCase(saveAnnotations.rejected, (state, action: AnyAction) => {
        state.saving = false
        state.error = action.error.message || 'Saving failed'
      })
      .addCase(fetchImage.fulfilled, (state, action: PayloadAction<FetchImageSuccess>) => {
        state.loading = false
        state.imageUrl = action.payload.url
        if (action.payload.annotations) state.annotations = action.payload.annotations
        if (action.payload.manualRqi) state.manualRqi = action.payload.manualRqi
        if (action.payload.tags) state.tags = action.payload.tags
        if (action.payload.manualComment) state.manualComment = action.payload.manualComment
        state.error = null
      })
      .addCase(fetchImage.rejected, (state, action: AnyAction) => {
        state.loading = false
        if (action.error.name !== 'AbortError' && action.error.message !== 'Aborted') {
          state.error = action.error.message || 'Failed to fetch image'
        }
      })
      .addCase(fetchList.pending, (state, action) => {
        state.loading = true
        state.error = null

        const payloadAction = action as unknown as PayloadAction<undefined, string, { arg: { mode: string; offset?: number } }>
        const offset = payloadAction.meta.arg.offset || 0
        if (offset === 0) {
          state.items = []
          state.offset = 0
          state.hasMore = false
          state.totalCount = 0
          state.navigationIds = []
        }
      })
      .addCase(fetchList.fulfilled, (state, action) => {
        state.loading = false
        
        const payloadAction = action as unknown as PayloadAction<FetchListSuccess, string, { arg: { mode: string; offset?: number } }>
        
        const offset = payloadAction.meta.arg.offset || 0
        state.items = payloadAction.payload.items

        state.totalCount = payloadAction.payload.totalCount
        state.hasMore = payloadAction.payload.hasMore
        state.offset = offset + state.items.length

        state.navigationIds = state.items.map(i => String(i.id))

        const mode = (payloadAction.meta.arg.mode || 'all').toLowerCase() as TrainingState['activeMode']
        state.activeMode = mode
      })
      .addCase(fetchList.rejected, (state, action: AnyAction) => {
        state.loading = false
        state.error = action.error.message || 'Failed to fetch list'
      })
      .addCase(fetchStats.fulfilled, (state, action: PayloadAction<TrainingStats>) => {
        state.globalStats = action.payload
      })
      
      // --- Async Job Handlers (Refactored) ---
      .addCase(runAnalysis.pending, (state) => {
        state.analysisStatus = 'running'
        state.analysisProgress = 0
        state.analysisTotal = 0
        state.analysisMessage = 'Kapcsolódás...'
        state.exports = null
      })
      .addCase(runAnalysis.fulfilled, (state, action: PayloadAction<{ jobId: string }>) => {
        state.analysisJobId = action.payload.jobId
        // Do NOT set status to 'running' here. The saga only completes when the poller finishes (attached fork).
        // By then, the job is likely 'completed' via updateJobProgress/jobCompleted.
        // Overwriting it here would revert the UI to running state improperly.
      })
      .addCase(runAnalysis.rejected, (state, action: AnyAction) => {
        state.analysisStatus = 'failed'
        state.analysisMessage = action.error.message || 'Start failed'
      })
      
      .addCase(startTraining.pending, (state) => {
        state.analysisStatus = 'running'
        state.trainingStatus = 'running'
        state.analysisMessage = 'Tanítás előkészítése...'
        state.exports = null
      })
      .addCase(startTraining.fulfilled, (state, action: PayloadAction<{ jobId: string }>) => {
        state.analysisJobId = action.payload.jobId
        // Same here: Do NOT reset status to 'running'. It's already handled by pending + poller.
      })
      .addCase(startTraining.rejected, (state, action: AnyAction) => {
        state.trainingStatus = 'failed'
        state.analysisStatus = 'failed'
        state.analysisMessage = action.error.message || 'Training start failed'
      })
      
      .addCase(stopJob.pending, (state) => {
        state.analysisMessage = 'Leállítás...'
      })
      // stopJob fulfilled/rejected handled by saga polling updates
      
  },
})

export const actions = {
  ...trainingSlice.actions,
  fetchImage,
  fetchList,
  fetchStats,
  saveAnnotations,
  deleteTrainingData,
  autoDetect,
  reconnectJob,
  runAnalysis,
  startTraining,
  stopJob,
}
export default trainingSlice.reducer
