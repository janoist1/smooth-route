import { createSlice } from '@reduxjs/toolkit'
import type { PayloadAction } from '@reduxjs/toolkit'
import { createSagaAction } from 'saga-toolkit'
import type { MapState, RoadPoint, RoadPointDetail } from './types'

const initialState: MapState = {
  points: [],
  loading: false,
  error: null,
  selectedPointId: null,
  selectedPointDetail: null,
  loadingDetail: false,
  viewport: {
    center: [47.4979, 19.0402], // Default Budapest
    zoom: 13,
  },
}

export const fetchPoints = createSagaAction<number[] | undefined, RoadPoint[]>('map/fetchPoints')
export const fetchPointDetail = createSagaAction<number, RoadPointDetail>('map/fetchPointDetail')

const mapSlice = createSlice({
  name: 'map',
  initialState,
  reducers: {
    selectPoint(state, action: PayloadAction<number | null>) {
      state.selectedPointId = action.payload
      if (action.payload === null) {
        state.selectedPointDetail = null
      }
    },
    setViewport(state, action: PayloadAction<{ center: [number, number]; zoom: number }>) {
      state.viewport = action.payload
    },
  },
  extraReducers: builder => {
    builder
      .addCase(fetchPoints.pending, state => {
        state.loading = true
        state.error = null
      })
      .addCase(fetchPoints.fulfilled, (state, action: PayloadAction<RoadPoint[]>) => {
        state.loading = false
        state.points = action.payload
      })
      .addCase(fetchPoints.rejected, (state, action) => {
        state.loading = false
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        state.error = (action as any).error?.message || 'Failed to fetch points'
      })
      .addCase(fetchPointDetail.pending, state => {
        state.loadingDetail = true
        state.selectedPointDetail = null
      })
      .addCase(fetchPointDetail.fulfilled, (state, action: PayloadAction<RoadPointDetail>) => {
        state.loadingDetail = false
        state.selectedPointDetail = action.payload
      })
      .addCase(fetchPointDetail.rejected, state => {
        state.loadingDetail = false
      })
  },
})

export const actions = { ...mapSlice.actions, fetchPoints, fetchPointDetail }
export default mapSlice.reducer
