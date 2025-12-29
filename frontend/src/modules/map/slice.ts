import { createSlice } from '@reduxjs/toolkit'
import type { PayloadAction } from '@reduxjs/toolkit'
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

const mapSlice = createSlice({
  name: 'map',
  initialState,
  reducers: {
    // eslint-disable-next-line @typescript-eslint/no-unused-vars
    fetchPoints(state, _action: PayloadAction<number[] | undefined>) {
      state.loading = true
      state.error = null
    },
    fetchPointsSuccess(state, action: PayloadAction<RoadPoint[]>) {
      state.loading = false
      state.points = action.payload
    },
    fetchPointsFailure(state, action: PayloadAction<string>) {
      state.loading = false
      state.error = action.payload
    },
    selectPoint(state, action: PayloadAction<number | null>) {
      state.selectedPointId = action.payload
      if (action.payload === null) {
        state.selectedPointDetail = null
      }
    },
    // eslint-disable-next-line @typescript-eslint/no-unused-vars
    fetchPointDetail(state, _action: PayloadAction<number>) {
      state.loadingDetail = true
      state.selectedPointDetail = null
    },
    fetchPointDetailSuccess(state, action: PayloadAction<RoadPointDetail>) {
      state.loadingDetail = false
      state.selectedPointDetail = action.payload
    },
    fetchPointDetailFailure(state) {
      state.loadingDetail = false
      // error logic for detail?
    },
    setViewport(state, action: PayloadAction<{ center: [number, number]; zoom: number }>) {
      state.viewport = action.payload
    },
  },
})

export const actions = mapSlice.actions
export default mapSlice.reducer
