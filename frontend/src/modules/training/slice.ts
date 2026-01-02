import { createSlice } from '@reduxjs/toolkit'
import type { PayloadAction } from '@reduxjs/toolkit'
import { createSagaAction } from 'saga-toolkit'
import type { TrainingState, AnnotationBox, TrainingPoint, TrainingStats } from './types'

// Actions
interface FetchImageSuccess {
  url: string
  manualRqi: number | null
  tags: string[]
  annotations: AnnotationBox[]
  manualComment: string | null
}

interface FetchListSuccess {
  items: TrainingPoint[]
  totalCount: number
  hasMore: boolean
}

export const fetchImage = createSagaAction<number, FetchImageSuccess>('training/fetchImage')
export const fetchList = createSagaAction<{ mode: string; offset?: number }, FetchListSuccess>('training/fetchList')
export const fetchStats = createSagaAction<{ mode: string }, TrainingStats>('training/fetchStats')
export const saveAnnotations = createSagaAction<void, { rqi: number | null; tags: string[]; comment: string }>('training/saveAnnotations')

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
  globalStats: null
}

const trainingSlice = createSlice({
  name: 'training',
  initialState,
  reducers: {
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
    },

    // Annotation Actions
    addAnnotation(state, action: PayloadAction<AnnotationBox>) {
      state.annotations.push(action.payload)
    },
    removeAnnotation(state, action: PayloadAction<string>) {
      state.annotations = state.annotations.filter(a => a.id !== action.payload)
    },
    updateAnnotation(state, action: PayloadAction<AnnotationBox>) {
      const index = state.annotations.findIndex(a => a.id === action.payload.id)
      if (index !== -1) {
        state.annotations[index] = action.payload
      }
    },
    setTool(state, action: PayloadAction<TrainingState['selectedTool']>) {
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
    setSettings(state, action: PayloadAction<{ rqi: number | null; tags: string[]; comment: string }>) {
      if (action.payload.rqi !== undefined) state.manualRqi = action.payload.rqi
      if (action.payload.tags !== undefined) state.tags = action.payload.tags
      if (action.payload.comment !== undefined) state.manualComment = action.payload.comment
    },
    updateJobProgress(state, action: PayloadAction<{ progress: number; total: number; message: string; status?: TrainingState['analysisStatus'] }>) {
      state.analysisProgress = action.payload.progress
      state.analysisTotal = action.payload.total
      state.analysisMessage = action.payload.message
      if (action.payload.status) {
        state.analysisStatus = action.payload.status
      }
    },
    setAnalysisStatus(state, action: PayloadAction<TrainingState['analysisStatus']>) {
      state.analysisStatus = action.payload
    },
    // Standard Actions for Sagas
    // eslint-disable-next-line @typescript-eslint/no-unused-vars
    runAnalysis(state, _action: PayloadAction<{ strategy: string; limit: number; reanalyze: boolean }>) {
      state.analysisStatus = 'running'
      state.analysisProgress = 0
      state.analysisTotal = 0
      state.analysisMessage = 'Kapcsolódás...'
    },
    runAnalysisSuccess(state, action: PayloadAction<{ jobId: string }>) {
      state.analysisJobId = action.payload.jobId
      state.analysisStatus = 'running'
    },
    runAnalysisFailure(state, action: PayloadAction<string>) {
      state.analysisStatus = 'failed'
      state.analysisMessage = action.payload
    },
    startTraining(state) {
      state.analysisStatus = 'running'
      state.trainingStatus = 'running'
      state.analysisMessage = 'Tanítás előkészítése...'
    },
    startTrainingSuccess(state, action: PayloadAction<{ jobId: string }>) {
      state.analysisJobId = action.payload.jobId
      state.trainingStatus = 'running'
      state.analysisStatus = 'running'
    },
    startTrainingFailure(state, action: PayloadAction<string>) {
      state.trainingStatus = 'failed'
      state.analysisStatus = 'failed'
      state.analysisMessage = action.payload
    },
    stopJob(state) {
      state.analysisMessage = 'Leállítás...'
    },
    resetAnalysisJob(state) {
      state.analysisJobId = null
      state.analysisProgress = 0
      state.analysisTotal = 0
      state.analysisStatus = 'idle'
      state.analysisMessage = ''
    },
  },
  extraReducers: builder => {
    builder
      .addCase(fetchImage.pending, (state, action) => {
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        const newId = (action as any).meta.arg.toString()
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
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      .addCase(saveAnnotations.fulfilled, (state, action: any) => {
        state.saving = false
        if (action.payload) {
          state.lastSavedSettings = {
            rqi: action.payload.rqi,
            tags: [...action.payload.tags],
            comment: action.payload.comment,
          }
        }
      })
      .addCase(saveAnnotations.rejected, (state, action) => {
        state.saving = false
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        state.error = (action as any).error.message || 'Saving failed'
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
      .addCase(fetchImage.rejected, (state, action) => {
        state.loading = false
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        const err = (action as any).error
        if (err.name !== 'AbortError' && err.message !== 'Aborted') {
          state.error = err.message || 'Failed to fetch image'
        }
      })
      .addCase(fetchList.pending, (state, action) => {
        state.loading = true
        state.error = null

        // Declarative Reset: if offset is 0 (or undefined), clear the list state
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        const offset = (action as any).meta.arg.offset || 0
        if (offset === 0) {
          state.items = []
          state.offset = 0
          state.hasMore = false
          state.totalCount = 0
          state.navigationIds = []
        }
      })
      .addCase(fetchList.fulfilled, (state, action: PayloadAction<FetchListSuccess>) => {
        state.loading = false
        // Handle Append vs Replace
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        const offset = (action as any).meta.arg.offset || 0
        if (offset === 0) {
          state.items = action.payload.items
        } else {
          state.items = [...state.items, ...action.payload.items]
        }
        
        state.totalCount = action.payload.totalCount
        state.hasMore = action.payload.hasMore
        state.offset = offset + action.payload.items.length

        state.navigationIds = state.items.map(i => String(i.id))
        
        // Update activeMode from the fetch request
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        const mode = ((action as any).meta.arg.mode || 'all').toLowerCase() as any
        state.activeMode = mode
      })
      .addCase(fetchList.rejected, (state, action) => {
        state.loading = false
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        const err = (action as any).error
        state.error = err.message || 'Failed to fetch list'
      })
      .addCase(fetchStats.fulfilled, (state, action: PayloadAction<TrainingStats>) => {
        state.globalStats = action.payload
      })
  },
})

export const actions = { ...trainingSlice.actions, fetchImage, fetchList, fetchStats, saveAnnotations }
export default trainingSlice.reducer
