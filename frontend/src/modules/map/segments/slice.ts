// State for the road-segment layer and the route quality summary. Kept in its
// own slice (store key `roads`) next to the map slice: it reacts to the map's
// route actions through extraReducers instead of widening MapState.
import { createSlice } from '@reduxjs/toolkit'
import type { PayloadAction, SerializedError } from '@reduxjs/toolkit'
import { createSagaAction } from 'saga-toolkit'
import { actions as mapActions } from '../slice'
import type { RoadPoint } from '../types'
import { pathBounds } from './geometry'
import type { LatLng, RoadSegment, RoadSegmentsState, RouteQuality } from './types'

// Request ids are internal bookkeeping (not part of the public state type):
// a superseded request's late `rejected` must not clear the newer one's flag.
interface InternalState extends RoadSegmentsState {
  segmentsRequestId: string | null
  routeQualityRequestId: string | null
}

export const initialState: InternalState = {
  items: [],
  loading: false,
  error: null,
  supported: true,
  lastQuery: null,
  selected: null,
  frames: [],
  routeQuality: null,
  routeQualityLoading: false,
  routeQualityError: null,
  focus: null,
  segmentsRequestId: null,
  routeQualityRequestId: null,
}

// createSagaAction<Returned, ThunkArg> — same order as the map slice.
export const fetchSegments = createSagaAction<RoadSegment[], { bbox: number[]; zoom: number }>(
  'roads/fetchSegments',
)
export const fetchSegmentFrames = createSagaAction<RoadPoint[], RoadSegment>(
  'roads/fetchSegmentFrames',
)
// null = the backend has no routeQuality yet (older deploy): show nothing.
export const fetchRouteQuality = createSagaAction<RouteQuality | null, LatLng[]>(
  'roads/fetchRouteQuality',
)

type Rejected = PayloadAction<unknown, string, { requestId: string }, SerializedError>

const isAbort = (error: SerializedError) =>
  error.name === 'AbortError' || error.message === 'Aborted'

const roadsSlice = createSlice({
  name: 'roads',
  initialState,
  reducers: {
    /** Select a segment (opens its card) or clear the selection with null. */
    selectSegment(state, action: PayloadAction<RoadSegment | null>) {
      if (state.selected?.id !== action.payload?.id) state.frames = []
      state.selected = action.payload
    },
    /** Select a segment AND ask the map to fit it (route summary → map). */
    focusSegment(state, action: PayloadAction<RoadSegment>) {
      if (state.selected?.id !== action.payload.id) state.frames = []
      state.selected = action.payload
      const bounds = pathBounds(action.payload.path)
      if (bounds) state.focus = { bounds, seq: (state.focus?.seq ?? 0) + 1 }
    },
    /** The backend does not know the segment API: fall back to grid/points. */
    markUnsupported(state) {
      state.supported = false
      state.items = []
      state.selected = null
      state.frames = []
    },
  },
  extraReducers: builder => {
    builder
      // Viewport segments
      .addCase(fetchSegments.pending, (state, action) => {
        state.loading = true
        state.error = null
        state.lastQuery = action.meta.arg
        state.segmentsRequestId = action.meta.requestId
      })
      .addCase(fetchSegments.fulfilled, (state, action) => {
        if (action.meta.requestId !== state.segmentsRequestId) return
        state.loading = false
        state.items = action.payload
      })
      .addCase(fetchSegments.rejected, (state, _action) => {
        const action = _action as Rejected
        if (action.meta.requestId !== state.segmentsRequestId) return
        state.loading = false
        if (!isAbort(action.error)) {
          state.error = action.error.message || 'Az útszakaszok betöltése nem sikerült'
        }
      })

      // Frames near the selected segment
      .addCase(fetchSegmentFrames.fulfilled, (state, action) => {
        if (state.selected?.id === action.meta.arg.id) state.frames = action.payload
      })

      // Route quality
      .addCase(fetchRouteQuality.pending, (state, action) => {
        state.routeQualityLoading = true
        state.routeQualityError = null
        state.routeQuality = null
        state.routeQualityRequestId = action.meta.requestId
      })
      .addCase(fetchRouteQuality.fulfilled, (state, action) => {
        if (action.meta.requestId !== state.routeQualityRequestId) return
        state.routeQualityLoading = false
        state.routeQuality = action.payload
      })
      .addCase(fetchRouteQuality.rejected, (state, _action) => {
        const action = _action as Rejected
        if (action.meta.requestId !== state.routeQualityRequestId) return
        state.routeQualityLoading = false
        if (!isAbort(action.error)) {
          state.routeQualityError = action.error.message || 'Az útvonal minősége nem érhető el'
        }
      })

      // Map slice events this state follows
      .addCase(mapActions.planRoute.pending, state => {
        // A new route is being planned: the old summary no longer applies.
        state.routeQuality = null
        state.routeQualityError = null
        state.routeQualityLoading = false
        state.routeQualityRequestId = null
      })
      .addCase(mapActions.clearRoute, state => {
        state.routeQuality = null
        state.routeQualityError = null
        state.routeQualityLoading = false
        state.routeQualityRequestId = null
      })
      .addCase(mapActions.startPickingLocation, state => {
        // Same as the point card: picking a location clears the selection.
        state.selected = null
        state.frames = []
      })
  },
})

export const actions = {
  ...roadsSlice.actions,
  fetchSegments,
  fetchSegmentFrames,
  fetchRouteQuality,
}
export default roadsSlice.reducer
