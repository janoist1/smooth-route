import { useMemo } from 'react'
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
  fetchPoints: (bbox?: number[]) => void
  selectPoint: (id: number | null) => void
  setViewport: (viewport: { center: [number, number]; zoom: number }) => void
  viewport: { center: [number, number]; zoom: number }
}

export const useMap = (): UseMap => {
  const dispatch = useDispatch()

  const points = useSelector(selectors.selectPoints)
  const loading = useSelector(selectors.selectLoading)
  const selectedPoint = useSelector(selectors.selectSelectedPoint)
  const selectedPointDetail = useSelector(selectors.selectSelectedPointDetail)
  const loadingDetail = useSelector(selectors.selectLoadingDetail)
  const viewport = useSelector(selectors.selectViewport)

  // Bind simple actions
  const boundActions = useMemo(() => bindActionCreators(actions, dispatch), [dispatch])

  return {
    points,
    loading,
    selectedPoint,
    selectedPointDetail,
    loadingDetail,
    viewport,
    ...boundActions, // fetchPoints, selectPoint, setViewport
  }
}
