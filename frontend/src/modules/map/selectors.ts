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
