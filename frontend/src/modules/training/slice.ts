import { createSlice, createAction } from '@reduxjs/toolkit'
import type { PayloadAction, SerializedError } from '@reduxjs/toolkit'
import { createSagaAction } from 'saga-toolkit'
import type { TrainingState, Annotation, TrainingPoint, TrainingStats, DamageLabel } from './types'
import { filterAnnotationsNMS } from './utils'

type SagaRejectedAction = PayloadAction<unknown, string, never, SerializedError>

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

export const fetchImage = createSagaAction<FetchImageSuccess, number>('training/fetchImage')
export const fetchList = createSagaAction<FetchListSuccess, { mode: string; offset?: number; model?: string }>(
  'training/fetchList',
)
export const fetchStats = createSagaAction<TrainingStats, { mode: string; model?: string }>('training/fetchStats')
export const saveAnnotations = createSagaAction<
  { rqi: number | null; tags: string[]; comment: string },
  void
>('training/saveAnnotations')
export const deleteTrainingData = createSagaAction<void, string>('training/deleteTrainingData')

// Unified Review Action
export const performReviewAction = createSagaAction<
  { annotations?: Annotation[]; processedImageUrl?: string; message?: string },
  { actionType: string; params: Record<string, unknown> }
>('training/performReviewAction')


// DINO Classification Actions
export const fetchDinoList = createSagaAction<
  { items: TrainingPoint[]; totalCount: number; offset: number; hasMore: boolean },
  { offset: number; mode?: string }
>('training/fetchDinoList')
// fetchDinoStats removed - use fetchStats({ model: 'dino' })
export const fetchDinoImage = createSagaAction<
  { id: string; url: string; manualRqi: number | null },
  number
>('training/fetchDinoImage')
export const saveDinoRqi = createSagaAction<{ nextId: number | null }, void>(
  'training/saveDinoRqi',
)
export const predictDinoRqi = createSagaAction<number | null, void>('training/predictDinoRqi')

// Job Actions
// Job Actions
export const reconnectJob = createAction('training/reconnectJob')
export const runAnalysis = createSagaAction<
  { jobId: string },
  { strategy: string; limit: number; reanalyze: boolean }
>('training/runAnalysis')
export const startTraining = createSagaAction<{ jobId: string }, { modelType?: string } | void>('training/startTraining')
export const stopJob = createSagaAction<void, string>('training/stopJob')

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
  autoDetectClasses: [
    'long_crack',
    'trans_crack',
    'alligator_crack',
    'pothole',
    'patch',
    'degradation',
    'shadow',
    'manhole',
    'marking',
    'ignore',
  ],
  
  // New: Track specific action loading
  loadingAction: null,
  previewUrl: null, // For preprocessing preview
}

const trainingSlice = createSlice({
  name: 'training',
  initialState,
  reducers: {
    setAutoDetectClasses(state, action: PayloadAction<string[]>) {
      state.autoDetectClasses = action.payload
    },
    // Lifecycle
    // unmount(state) {
    //   state.imageId = null
    //   state.imageUrl = null
    //   state.annotations = []
    //   state.tags = []
    //   state.manualRqi = null
    //   state.manualComment = ''
    //   state.error = null
    //   state.loading = false
    //   state.lastSavedSettings = null
    //   state.exports = null
    //   state.loadingAction = null
    // },

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
      state.trainingStatus = 'completed'
      state.analysisJobId = null
      state.exports = action.payload?.exports || null
    },
    resetAnalysisJob(state) {
      state.analysisJobId = null
      state.exports = null
      state.trainingStatus = 'idle'
    },
    setAnalysisJobId(state, action: PayloadAction<string>) {
      state.analysisJobId = action.payload
    },
    clearPreview(state) {
        state.previewUrl = null
    }
  },
  extraReducers: builder => {
    builder
      .addCase(performReviewAction.pending, (state, action) => {
          // Track which action is running for granular spinners
          // action.meta.arg contains { actionType, params }
          const arg = action.meta.arg as { actionType: string } | undefined
          state.loadingAction = arg?.actionType || 'unknown'
          state.error = null
      })
      .addCase(performReviewAction.fulfilled, (state, action) => {
          state.loadingAction = null
          const result = action.payload
          
          if (result.annotations) {
              state.annotations.push(...result.annotations)
          }
          if (result.processedImageUrl) {
              state.previewUrl = result.processedImageUrl
          }
      })
      .addCase(performReviewAction.rejected, (state, action) => {
          state.loadingAction = null
          const rej = action as SagaRejectedAction
          state.error = rej.error.message || 'Action failed'
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
          state.previewUrl = null // Clear preview on new image
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
      .addCase(
        saveAnnotations.fulfilled,
        (state, action: PayloadAction<{ rqi: number | null; tags: string[]; comment: string }>) => {
          state.saving = false
          if (action.payload) {
            state.lastSavedSettings = {
              rqi: action.payload.rqi,
              tags: [...action.payload.tags],
              comment: action.payload.comment,
            }
          }
        },
      )
      .addCase(saveAnnotations.rejected, (state, _action) => {
        const action = _action as SagaRejectedAction
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
      .addCase(fetchImage.rejected, (state, _action) => {
        const action = _action as SagaRejectedAction
        state.loading = false
        if (action.error.name !== 'AbortError' && action.error.message !== 'Aborted') {
          state.error = action.error.message || 'Failed to fetch image'
        }
      })
      .addCase(fetchList.pending, (state, action) => {
        state.loading = true
        state.error = null

        const payloadAction = action as unknown as PayloadAction<
          undefined,
          string,
          { arg: { mode: string; offset?: number; model?: string } }
        >
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

        const payloadAction = action as unknown as PayloadAction<
          FetchListSuccess,
          string,
          { arg: { mode: string; offset?: number; model?: string } }
        >

        const offset = payloadAction.meta.arg.offset || 0
        state.items = payloadAction.payload.items
        state.totalCount = payloadAction.payload.totalCount
        state.hasMore = payloadAction.payload.hasMore
        
        // Update offset to the current page's start offset
        state.offset = offset

        state.navigationIds = state.items.map(i => String(i.id))

        const mode = (
          payloadAction.meta.arg.mode || 'all'
        ).toLowerCase() as TrainingState['activeMode']
        state.activeMode = mode
      })
      .addCase(fetchList.rejected, (state, _action) => {
        const action = _action as SagaRejectedAction
        state.loading = false
        state.error = action.error.message || 'Failed to fetch list'
      })
      .addCase(fetchStats.fulfilled, (state, action: PayloadAction<TrainingStats>) => {
        state.globalStats = action.payload
      })

      // --- Async Job Handlers (Refactored) ---
      .addCase(runAnalysis.pending, state => {
         // Placeholder for pending state if needed
         state.exports = null
      })
      .addCase(runAnalysis.fulfilled, (state, action: PayloadAction<{ jobId: string }>) => {
        state.analysisJobId = action.payload.jobId
      })
      // rejected handled generically or via API slice error

      .addCase(startTraining.pending, state => {
        state.trainingStatus = 'running'
        state.exports = null
      })
      .addCase(startTraining.fulfilled, (state, action: PayloadAction<{ jobId: string }>) => {
        state.analysisJobId = action.payload.jobId
      })
      .addCase(startTraining.rejected, (state) => {
        state.trainingStatus = 'failed'
      })
      // DINO Classification Reducers
      .addCase(fetchDinoList.pending, (state) => {
        state.loading = true
        state.error = null
      })
      .addCase(fetchDinoList.fulfilled, (state, action: PayloadAction<{ items: TrainingPoint[]; totalCount: number; offset: number }>) => {
        state.loading = false
        state.items = action.payload.offset === 0 
          ? action.payload.items 
          : [...state.items, ...action.payload.items]
        state.totalCount = action.payload.totalCount
        state.offset = action.payload.offset + action.payload.items.length
      })
      .addCase(fetchDinoList.rejected, (state, _action) => {
        const action = _action as SagaRejectedAction
        state.loading = false
        if (action.error.name !== 'AbortError' && action.error.message !== 'Aborted') {
          state.error = action.error?.message || 'Failed to fetch DINO list'
        }
      })

      .addCase(fetchDinoImage.pending, (state) => {
        state.loading = true
        state.error = null
      })
      .addCase(fetchDinoImage.fulfilled, (state, action: PayloadAction<{ id: string; url: string; manualRqi: number | null }>) => {
        state.loading = false
        state.imageId = action.payload.id
        state.imageUrl = action.payload.url
        state.manualRqi = action.payload.manualRqi
      })
      .addCase(fetchDinoImage.rejected, (state, _action) => {
        const action = _action as SagaRejectedAction
        state.loading = false
        if (action.error.name !== 'AbortError' && action.error.message !== 'Aborted') {
          state.error = action.error?.message || 'Failed to fetch DINO image'
        }
      })
      .addCase(saveDinoRqi.pending, (state) => {
        state.saving = true
      })
      .addCase(saveDinoRqi.fulfilled, (state) => {
        state.saving = false
      })
      .addCase(saveDinoRqi.rejected, (state, _action) => {
        const action = _action as SagaRejectedAction
        state.saving = false
        state.error = action.error?.message || 'Failed to save DINO RQI'
      })
      .addCase(predictDinoRqi.pending, (state) => {
        state.loading = true
      })
      .addCase(predictDinoRqi.fulfilled, (state, action) => {
        state.loading = false
        if (action.payload) {
          state.manualRqi = action.payload
        }
      })
      .addCase(predictDinoRqi.rejected, (state, _action) => {
          const action = _action as SagaRejectedAction
          state.loading = false
          state.error = action.error?.message || 'Failed to predict DINO RQI'
      })
  },
})

export const actions = {
  ...trainingSlice.actions,
  fetchImage,
  fetchList,
  fetchStats,
  saveAnnotations,
  deleteTrainingData,
  performReviewAction,
  reconnectJob,
  runAnalysis,
  startTraining,
  stopJob,
  fetchDinoList,

  fetchDinoImage,
  saveDinoRqi,
  predictDinoRqi,
}
export default trainingSlice.reducer
