import { describe, it, expect } from 'vitest'
import type { RootState } from '../../store'
import { initialState } from './slice'
import * as selectors from './selectors'
import type { MapState, RoadPoint, RoadPointDetail } from './types'

const points: RoadPoint[] = [
  { id: 1, latitude: 47.5, longitude: 19.04 },
  { id: 2, latitude: 47.51, longitude: 19.05, dino_rqi_score: 3.4 },
]

const root = (map: Partial<MapState>): RootState => ({ map: { ...initialState, ...map } }) as unknown as RootState

describe('map selectors', () => {
  it('selectSelectedPoint finds the selected point among the loaded ones', () => {
    expect(selectors.selectSelectedPoint(root({ points, selectedPointId: 2 }))).toBe(points[1])
  })

  it('selectSelectedPoint is null with no selection or when the point is not loaded', () => {
    expect(selectors.selectSelectedPoint(root({ points, selectedPointId: null }))).toBeNull()
    expect(selectors.selectSelectedPoint(root({ points, selectedPointId: 99 }))).toBeNull()
    expect(selectors.selectSelectedPoint(root({ points: [], selectedPointId: 1 }))).toBeNull()
  })

  it('exposes every plain field of the map state', () => {
    const detail = { id: 2, image_url: '/images/2.jpg' } as RoadPointDetail
    const grid = { cell: 0.01, cells: [] }
    const state = root({
      points,
      grid,
      loading: true,
      selectedPointId: 2,
      selectedPointDetail: detail,
      loadingDetail: true,
      routePoints: [[47, 19]],
      routeAlternatives: [],
      selectedRouteIndex: 1,
      isPlanningRoute: true,
      isAnalyzingRoute: true,
      routeAnalysisJobId: 'job-1',
      error: 'hiba',
      origin: 'Szeged',
      destination: 'Pécs',
      pickingLocationFor: 'origin',
    })

    expect(selectors.selectPoints(state)).toBe(points)
    expect(selectors.selectGrid(state)).toBe(grid)
    expect(selectors.selectLoading(state)).toBe(true)
    expect(selectors.selectSelectedPointId(state)).toBe(2)
    expect(selectors.selectSelectedPointDetail(state)).toBe(detail)
    expect(selectors.selectLoadingDetail(state)).toBe(true)
    expect(selectors.selectViewport(state)).toEqual(initialState.viewport)
    expect(selectors.selectRoutePoints(state)).toEqual([[47, 19]])
    expect(selectors.selectRouteAlternatives(state)).toEqual([])
    expect(selectors.selectSelectedRouteIndex(state)).toBe(1)
    expect(selectors.selectIsPlanningRoute(state)).toBe(true)
    expect(selectors.selectIsAnalyzingRoute(state)).toBe(true)
    expect(selectors.selectRouteAnalysisJobId(state)).toBe('job-1')
    expect(selectors.selectError(state)).toBe('hiba')
    expect(selectors.selectOrigin(state)).toBe('Szeged')
    expect(selectors.selectDestination(state)).toBe('Pécs')
    expect(selectors.selectPickingLocationFor(state)).toBe('origin')
  })
})
