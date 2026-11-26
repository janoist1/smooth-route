import { createSlice, createAction } from '@reduxjs/toolkit'
import type { RouteAlternative } from './alternatives'
import type { PayloadAction } from '@reduxjs/toolkit'
import { createSagaAction } from 'saga-toolkit'
import type { MapState, RoadPoint, RoadPointDetail } from './types'
import type { QualityGrid } from './aggregation'
import type { SerializedError } from '@reduxjs/toolkit'

type SagaRejectedAction = PayloadAction<unknown, string, never, SerializedError>

export const initialState: MapState = {
  points: [],
  grid: null,
  loading: false,
  error: null,
  selectedPointId: null,
  selectedPointDetail: null,
  loadingDetail: false,
  viewport: {
    center: [47.4979, 19.0402], // Default Budapest
    zoom: 13,
  },
  routePoints: null,
  routeAlternatives: null,
  selectedRouteIndex: null,
  isPlanningRoute: false,
  isAnalyzingRoute: false,
  routeAnalysisJobId: null,
  origin: 'Budapest, Aulich utca 1.',
  destination: 'Székesfehérvár',
  pickingLocationFor: null,
}

// saga-toolkit's createSagaAction takes <Returned, ThunkArg> (matching RTK's
// createAsyncThunk), so the resolved payload comes first and the dispatch arg
// second — same order the training/settings modules use.
export const fetchPoints = createSagaAction<RoadPoint[], number[] | undefined>('map/fetchPoints')
export const fetchGrid = createSagaAction<QualityGrid, { bbox?: number[]; zoom: number }>(
  'map/fetchGrid',
)
export const fetchPointDetail = createSagaAction<RoadPointDetail, number>('map/fetchPointDetail')

export const planRoute = createSagaAction<[number, number][], { origin: string; destination: string }>('map/planRoute')
export const analyzeRoute = createSagaAction<string, { origin: string; destination: string }>('map/analyzeRoute')

// Dispatched on map page load to restore a running route job from the backend.
export const reconnectRouteJob = createAction('map/reconnectRouteJob')

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
    
    // Route & Picking Logic
    setRouteForm(state, action: PayloadAction<{ field: 'origin' | 'destination'; value: string }>) {
      state[action.payload.field] = action.payload.value
    },
    startPickingLocation(state, action: PayloadAction<'origin' | 'destination'>) {
      state.pickingLocationFor = action.payload
      // Optionally deselect point to avoid clutter
      state.selectedPointId = null 
      state.selectedPointDetail = null
    },
    cancelPickingLocation(state) {
      state.pickingLocationFor = null
    },
    updatePickedLocation(state, action: PayloadAction<{ lat: number; lng: number }>) {
       if (state.pickingLocationFor) {
           // Simple "Lat, Lng" format for now
           const val = `${action.payload.lat.toFixed(6)}, ${action.payload.lng.toFixed(6)}`
           state[state.pickingLocationFor] = val
           state.pickingLocationFor = null
       }
    },

    finishAnalysis(state) {
      state.isAnalyzingRoute = false
    },

    // Re-attach the progress UI to a route job still running on the backend
    // (e.g. after a page reload, when routeAnalysisJobId was lost from memory).
    restoreRouteJob(state, action: PayloadAction<string>) {
      state.routeAnalysisJobId = action.payload
      state.isAnalyzingRoute = true
    },
                   
    setRouteAlternatives(state, action: PayloadAction<{ routes: RouteAlternative[]; selected: number | null }>) {
      state.routeAlternatives = action.payload.routes
      state.selectedRouteIndex = action.payload.selected
    },
    /** Show another of the planned alternatives (its quality is re-fetched). */
    selectRouteAlternative(state, action: PayloadAction<number>) {
      const route = state.routeAlternatives?.find(r => r.index === action.payload)
      if (!route) return
      state.selectedRouteIndex = route.index
      state.routePoints = route.points
    },
    clearRoute(state) {
      state.isPlanningRoute = false
      state.routeAlternatives = null
      state.selectedRouteIndex = null
      state.routePoints = null
      state.routeAnalysisJobId = null
      state.isAnalyzingRoute = false
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
        // Raw points and the quality grid are mutually exclusive views.
        state.grid = null
      })
      .addCase(fetchPoints.rejected, (state, _action) => {
        state.loading = false
        const action = _action as SagaRejectedAction
        // Ignore AbortErrors (cancelled requests)
        if (action.error.name !== 'AbortError' && action.error.message !== 'Aborted') {
          state.error = action.error.message || 'Failed to fetch points'
        }
      })

      // Quality-grid overview (zoomed out)
      .addCase(fetchGrid.pending, state => {
        state.loading = true
        state.error = null
      })
      .addCase(fetchGrid.fulfilled, (state, action: PayloadAction<QualityGrid>) => {
        state.loading = false
        state.grid = action.payload
        state.points = []
      })
      .addCase(fetchGrid.rejected, (state, _action) => {
        state.loading = false
        const action = _action as SagaRejectedAction
        if (action.error.name !== 'AbortError' && action.error.message !== 'Aborted') {
          state.error = action.error.message || 'Failed to fetch overview'
        }
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

      // Route Planner
      .addCase(planRoute.pending, state => {
        state.isPlanningRoute = true
        state.error = null
        state.routePoints = null
        state.routeAlternatives = null
        state.selectedRouteIndex = null
      })
      .addCase(planRoute.fulfilled, (state, action: PayloadAction<[number, number][]>) => {
        state.isPlanningRoute = false
        state.routePoints = action.payload
      })
      .addCase(planRoute.rejected, (state, _action) => {
        const action = _action as SagaRejectedAction
        if (action.error.name === 'AbortError' || action.error.message === 'Aborted') return
        state.isPlanningRoute = false
        state.error = action.error.message || 'Route planning failed'
      })

      // Route Analysis
      .addCase(analyzeRoute.pending, state => {
        state.isAnalyzingRoute = true
        state.error = null
        state.routeAnalysisJobId = null
      })
      .addCase(analyzeRoute.fulfilled, (state, action: PayloadAction<string>) => {
        state.routeAnalysisJobId = action.payload
      })
      .addCase(analyzeRoute.rejected, (state, _action) => {
        state.isAnalyzingRoute = false
        const action = _action as SagaRejectedAction
        state.error = action.error.message || 'Analysis start failed'
      })
  },
})

export const actions = { ...mapSlice.actions, fetchPoints, fetchGrid, fetchPointDetail, planRoute, analyzeRoute, reconnectRouteJob }
export default mapSlice.reducer
