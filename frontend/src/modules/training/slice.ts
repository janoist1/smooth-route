import { createSlice } from '@reduxjs/toolkit'
import type { PayloadAction } from '@reduxjs/toolkit'
import { createSagaAction } from 'saga-toolkit'
import type { TrainingState, AnnotationBox } from './types'

// Actions
interface FetchImageSuccess {
  url: string
  manualRqi: number | null
  tags: string[]
  annotations: AnnotationBox[]
  manualComment: string | null
}

export const fetchImage = createSagaAction<number, FetchImageSuccess>('training/fetchImage')
export const saveAnnotations = createSagaAction<void, void>('training/saveAnnotations')

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
    },

    // Annotation Actions
    addAnnotation(state, action: PayloadAction<AnnotationBox>) {
      state.annotations.push(action.payload)
    },
    removeAnnotation(state, action: PayloadAction<string>) {
      // id
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
  },
  extraReducers: builder => {
    builder
      .addCase(fetchImage.pending, (state, action) => {
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        const newId = (action as any).meta.arg.toString()
        // Only reset if ID changed (Orchestrator Pattern)
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
      })
      .addCase(saveAnnotations.fulfilled, state => {
        state.saving = false
      })
      .addCase(saveAnnotations.rejected, (state, action) => {
        state.saving = false
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        state.error = (action as any).error.message || 'Saving failed'
      })
      .addCase(fetchImage.fulfilled, (state, action: PayloadAction<FetchImageSuccess>) => {
        state.loading = false
        state.imageUrl = action.payload.url

        // Populate saved data if exists
        if (action.payload.annotations) state.annotations = action.payload.annotations
        if (action.payload.manualRqi) state.manualRqi = action.payload.manualRqi
        if (action.payload.tags) state.tags = action.payload.tags
        if (action.payload.manualComment) state.manualComment = action.payload.manualComment

        state.error = null
      })
      .addCase(fetchImage.rejected, (state, action) => {
        state.loading = false
        // Ignore Aborted errors (happens in StrictMode due to double-mount)
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        const err = (action as any).error
        if (err.name !== 'AbortError' && err.message !== 'Aborted') {
          state.error = err.message || 'Failed to fetch image'
        }
      })
  },
})

export const actions = { ...trainingSlice.actions, fetchImage, saveAnnotations }
export default trainingSlice.reducer
