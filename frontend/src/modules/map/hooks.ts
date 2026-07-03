import { useMemo } from 'react'
import { useSelector, useDispatch } from 'react-redux'
import { bindActionCreators } from '@reduxjs/toolkit'
import { actions } from './slice'
import * as selectors from './selectors'
import type { RoadPoint, RoadPointDetail } from './types'
import type { QualityGrid } from './aggregation'
import type { RootState } from '../../store'
import { selectJob } from '../api'

// Power Hook Interface: Combines State + Actions
export interface UseMap {
  points: RoadPoint[]
  grid: QualityGrid | null
  loading: boolean
  selectedPoint: RoadPoint | null
  selectedPointDetail: RoadPointDetail | null
  loadingDetail: boolean
  
  // Route Planner State
  isPlanningRoute: boolean
  isAnalyzingRoute: boolean
  routeAnalysisJobId: string | null
  error: string | null
  origin: string
  destination: string
  pickingLocationFor: 'origin' | 'destination' | null
  routePoints: [number, number][] | null
  
  // Job State
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  job: any

  // Actions
  fetchPoints: (bbox?: number[]) => void
  selectPoint: (id: number | null) => void
  setViewport: (viewport: { center: [number, number]; zoom: number }) => void
  viewport: { center: [number, number]; zoom: number }
  updatePickedLocation: (coords: { lat: number; lng: number }) => void
  
  // Route Actions
  planRoute: (args: { origin: string; destination: string }) => void
  analyzeRoute: (args: { origin: string; destination: string }) => void
  clearRoute: () => void
  setRouteForm: (payload: { field: 'origin' | 'destination'; value: string }) => void
  startPickingLocation: (field: 'origin' | 'destination') => void
  cancelPickingLocation: () => void
}

export const useMap = (): UseMap => {
  const dispatch = useDispatch()

  const points = useSelector(selectors.selectPoints)
  const grid = useSelector(selectors.selectGrid)
  const loading = useSelector(selectors.selectLoading)
  const selectedPoint = useSelector(selectors.selectSelectedPoint)
  const selectedPointDetail = useSelector(selectors.selectSelectedPointDetail)
  const loadingDetail = useSelector(selectors.selectLoadingDetail)
  const viewport = useSelector(selectors.selectViewport)

  // Route Planner State
  const routePoints = useSelector(selectors.selectRoutePoints)
  const isPlanningRoute = useSelector(selectors.selectIsPlanningRoute)
  const isAnalyzingRoute = useSelector(selectors.selectIsAnalyzingRoute)
  const routeAnalysisJobId = useSelector(selectors.selectRouteAnalysisJobId)
  const error = useSelector(selectors.selectError)
  const origin = useSelector(selectors.selectOrigin)
  const destination = useSelector(selectors.selectDestination)
  const pickingLocationFor = useSelector(selectors.selectPickingLocationFor)

  const job = useSelector((state: RootState) => selectJob(state, routeAnalysisJobId))

  // Bind simple actions
  const boundActions = useMemo(() => bindActionCreators(actions, dispatch), [dispatch])

  return {
    points,
    grid,
    loading,
    selectedPoint,
    selectedPointDetail,
    loadingDetail,
    viewport,
    
    // Route Planner
    routePoints,
    isPlanningRoute,
    isAnalyzingRoute,
    routeAnalysisJobId,
    error,
    origin,
    destination,
    pickingLocationFor,
    job,
    
    ...boundActions, 
  }
}
