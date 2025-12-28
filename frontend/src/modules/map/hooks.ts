import { useSelector, useDispatch } from 'react-redux'
import { bindActionCreators } from '@reduxjs/toolkit'
import { actions } from './slice'
import * as selectors from './selectors'
import type { RoadPoint, RoadPointDetail } from './types'

// Power Hook Interface: Combines State + Actions
export interface UseMap {
  points: RoadPoint[]
  loading: boolean
  selectedPoint: RoadPoint | null
  selectedPointDetail: RoadPointDetail | null
  loadingDetail: boolean
  fetchPoints: () => void
  selectPoint: (id: number | null) => void
}

export const useMap = (): UseMap => {
  const dispatch = useDispatch()

  const points = useSelector(selectors.selectPoints)
  const loading = useSelector(selectors.selectLoading)
  const selectedPoint = useSelector(selectors.selectSelectedPoint)
  const selectedPointDetail = useSelector(selectors.selectSelectedPointDetail)
  const loadingDetail = useSelector(selectors.selectLoadingDetail)

  // Bind simple actions
  const boundActions = bindActionCreators(actions, dispatch)

  return {
    points,
    loading,
    selectedPoint,
    selectedPointDetail,
    loadingDetail,
    ...boundActions, // fetchPoints, selectPoint
  }
}
