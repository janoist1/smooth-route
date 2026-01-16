import type { RootState } from '../../store'
import { createSelector } from '@reduxjs/toolkit'

const selectMapState = (state: RootState) => state.map

export const selectPoints = createSelector(selectMapState, map => map.points)

export const selectLoading = createSelector(selectMapState, map => map.loading)

export const selectSelectedPointId = createSelector(selectMapState, map => map.selectedPointId)

export const selectSelectedPoint = createSelector(
  selectPoints,
  selectSelectedPointId,
  (points, id) => (id ? points.find(p => p.id === id) || null : null),
)

export const selectSelectedPointDetail = createSelector(
  selectMapState,
  map => map.selectedPointDetail,
)

export const selectLoadingDetail = createSelector(selectMapState, map => map.loadingDetail)

export const selectViewport = createSelector(selectMapState, map => map.viewport)

export const selectRoutePoints = createSelector(selectMapState, map => map.routePoints)

export const selectIsPlanningRoute = createSelector(selectMapState, map => map.isPlanningRoute)
export const selectIsAnalyzingRoute = createSelector(selectMapState, map => map.isAnalyzingRoute)
export const selectRouteAnalysisJobId = createSelector(selectMapState, map => map.routeAnalysisJobId)
export const selectError = createSelector(selectMapState, map => map.error)
export const selectOrigin = createSelector(selectMapState, map => map.origin)
export const selectDestination = createSelector(selectMapState, map => map.destination)
export const selectPickingLocationFor = createSelector(selectMapState, map => map.pickingLocationFor)
