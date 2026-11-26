import type { RootState } from '../../../store'

export const selectRoads = (state: RootState) => state.roads

export const selectSegments = (state: RootState) => state.roads.items
export const selectSegmentsLoading = (state: RootState) => state.roads.loading
export const selectSegmentsError = (state: RootState) => state.roads.error
export const selectSegmentsSupported = (state: RootState) => state.roads.supported
export const selectLastSegmentQuery = (state: RootState) => state.roads.lastQuery
export const selectSelectedSegment = (state: RootState) => state.roads.selected
export const selectSegmentFrames = (state: RootState) => state.roads.frames
export const selectRouteQuality = (state: RootState) => state.roads.routeQuality
export const selectRouteQualityLoading = (state: RootState) => state.roads.routeQualityLoading
export const selectRouteQualityError = (state: RootState) => state.roads.routeQualityError
export const selectSegmentFocus = (state: RootState) => state.roads.focus
