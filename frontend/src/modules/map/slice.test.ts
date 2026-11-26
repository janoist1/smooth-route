import { describe, it, expect } from 'vitest'
import reducer, { actions, initialState } from './slice'
import type { RouteAlternative } from './alternatives'
import type { MapState, RoadPoint, RoadPointDetail } from './types'

const point = (id: number): RoadPoint => ({ id, latitude: 47.5, longitude: 19.04 })

const alternative = (index: number, lat: number): RouteAlternative =>
  ({
    index,
    points: [
      [lat, 19],
      [lat + 0.01, 19.01],
    ],
    distanceM: 1000,
    durationS: 120,
    summary: `M${index}`,
    coverage: 0.5,
    isFastest: index === 0,
    isSmoothest: index === 1,
  }) as RouteAlternative

const rejected = (type: string, error: { name?: string; message?: string }) => ({ type, error })

describe('map slice — selection and viewport', () => {
  it('selects a point and drops the detail when the selection is cleared', () => {
    const withDetail: MapState = { ...initialState, selectedPointDetail: { id: 3 } as RoadPointDetail }
    let s = reducer(withDetail, actions.selectPoint(3))
    expect(s.selectedPointId).toBe(3)
    expect(s.selectedPointDetail).not.toBeNull()

    s = reducer(s, actions.selectPoint(null))
    expect(s.selectedPointId).toBeNull()
    expect(s.selectedPointDetail).toBeNull()
  })

  it('stores the viewport', () => {
    const s = reducer(initialState, actions.setViewport({ center: [46.25, 20.15], zoom: 16 }))
    expect(s.viewport).toEqual({ center: [46.25, 20.15], zoom: 16 })
  })
})

describe('map slice — route form and map picking', () => {
  it('edits the origin and destination fields', () => {
    let s = reducer(initialState, actions.setRouteForm({ field: 'origin', value: 'Szeged' }))
    s = reducer(s, actions.setRouteForm({ field: 'destination', value: 'Pécs' }))
    expect(s).toMatchObject({ origin: 'Szeged', destination: 'Pécs' })
  })

  it('writes the picked coordinate into the field being picked, 6 decimals', () => {
    const selected: MapState = { ...initialState, selectedPointId: 9, selectedPointDetail: { id: 9 } as RoadPointDetail }
    let s = reducer(selected, actions.startPickingLocation('destination'))
    expect(s).toMatchObject({ pickingLocationFor: 'destination', selectedPointId: null, selectedPointDetail: null })

    s = reducer(s, actions.updatePickedLocation({ lat: 47.1234567, lng: 19.5 }))
    expect(s.destination).toBe('47.123457, 19.500000')
    expect(s.origin).toBe(initialState.origin)
    expect(s.pickingLocationFor).toBeNull()
  })

  it('ignores a picked coordinate when no field is being picked', () => {
    const s = reducer(initialState, actions.updatePickedLocation({ lat: 1, lng: 2 }))
    expect(s).toEqual(initialState)
  })

  it('cancels picking without touching the form', () => {
    let s = reducer(initialState, actions.startPickingLocation('origin'))
    s = reducer(s, actions.cancelPickingLocation())
    expect(s.pickingLocationFor).toBeNull()
    expect(s.origin).toBe(initialState.origin)
  })
})

describe('map slice — points and quality grid', () => {
  it('points and the grid are mutually exclusive views', () => {
    const grid = { cell: 0.01, cells: [[47.5, 19.04, 2.5] as [number, number, number]] }

    let s = reducer(initialState, { type: actions.fetchGrid.pending.type })
    expect(s.loading).toBe(true)
    s = reducer({ ...s, points: [point(1)] }, { type: actions.fetchGrid.fulfilled.type, payload: grid })
    expect(s).toMatchObject({ loading: false, grid, points: [] })

    s = reducer(s, { type: actions.fetchPoints.pending.type })
    expect(s).toMatchObject({ loading: true, error: null })
    s = reducer(s, { type: actions.fetchPoints.fulfilled.type, payload: [point(1), point(2)] })
    expect(s.loading).toBe(false)
    expect(s.points.map(p => p.id)).toEqual([1, 2])
    expect(s.grid).toBeNull()
  })

  it.each([
    ['fetchPoints', actions.fetchPoints.rejected.type, 'Failed to fetch points'],
    ['fetchGrid', actions.fetchGrid.rejected.type, 'Failed to fetch overview'],
  ])('%s reports failures but not cancelled requests', (_name, type, fallback) => {
    const loading: MapState = { ...initialState, loading: true }

    expect(reducer(loading, rejected(type, { message: 'HTTP 500' }))).toMatchObject({ loading: false, error: 'HTTP 500' })
    expect(reducer(loading, rejected(type, {})).error).toBe(fallback)
    expect(reducer(loading, rejected(type, { name: 'AbortError', message: 'cancelled' }))).toMatchObject({
      loading: false,
      error: null,
    })
    expect(reducer(loading, rejected(type, { message: 'Aborted' })).error).toBeNull()
  })

  it('tracks the point detail request', () => {
    const detail = { id: 5, image_url: '/images/5.jpg', damage_count: 2, created_at: '2026-01-01' } as RoadPointDetail

    let s = reducer({ ...initialState, selectedPointDetail: detail }, { type: actions.fetchPointDetail.pending.type })
    expect(s).toMatchObject({ loadingDetail: true, selectedPointDetail: null })

    s = reducer(s, { type: actions.fetchPointDetail.fulfilled.type, payload: detail })
    expect(s).toMatchObject({ loadingDetail: false, selectedPointDetail: detail })

    s = reducer({ ...s, loadingDetail: true }, { type: actions.fetchPointDetail.rejected.type })
    expect(s.loadingDetail).toBe(false)
  })
})

describe('map slice — route planning', () => {
  const planned: MapState = {
    ...initialState,
    routePoints: [[47, 19]],
    routeAlternatives: [alternative(0, 47), alternative(1, 48)],
    selectedRouteIndex: 0,
    error: 'old',
  }

  it('a new plan clears the previous route and its alternatives', () => {
    let s = reducer(planned, { type: actions.planRoute.pending.type })
    expect(s).toMatchObject({
      isPlanningRoute: true,
      error: null,
      routePoints: null,
      routeAlternatives: null,
      selectedRouteIndex: null,
    })

    s = reducer(s, { type: actions.planRoute.fulfilled.type, payload: [[47, 19], [47.1, 19.1]] })
    expect(s.isPlanningRoute).toBe(false)
    expect(s.routePoints).toHaveLength(2)
  })

  it('surfaces a planning failure', () => {
    const busy: MapState = { ...initialState, isPlanningRoute: true }
    expect(reducer(busy, rejected(actions.planRoute.rejected.type, { message: 'ZERO_RESULTS' }))).toMatchObject({
      isPlanningRoute: false,
      error: 'ZERO_RESULTS',
    })
    expect(reducer(busy, rejected(actions.planRoute.rejected.type, {})).error).toBe('Route planning failed')
  })

  it('stores the alternatives and switches the drawn route between them', () => {
    let s = reducer(initialState, actions.setRouteAlternatives({ routes: [alternative(0, 47), alternative(1, 48)], selected: 1 }))
    expect(s.routeAlternatives).toHaveLength(2)
    expect(s.selectedRouteIndex).toBe(1)

    s = reducer(s, actions.selectRouteAlternative(0))
    expect(s.selectedRouteIndex).toBe(0)
    expect(s.routePoints).toEqual(alternative(0, 47).points)
  })

  it('ignores an unknown alternative index (also when none are planned)', () => {
    expect(reducer(planned, actions.selectRouteAlternative(7))).toEqual(planned)
    expect(reducer(initialState, actions.selectRouteAlternative(0))).toEqual(initialState)
  })

  it('clearRoute forgets the route, its alternatives and the analysis job', () => {
    const s = reducer({ ...planned, routeAnalysisJobId: 'job-1', isAnalyzingRoute: true }, actions.clearRoute())
    expect(s).toMatchObject({
      routeAlternatives: null,
      selectedRouteIndex: null,
      routePoints: null,
      routeAnalysisJobId: null,
      isAnalyzingRoute: false,
    })
  })
})

describe('map slice — route analysis job', () => {
  it('follows the job from start to finish', () => {
    let s = reducer({ ...initialState, routeAnalysisJobId: 'old', error: 'old' }, { type: actions.analyzeRoute.pending.type })
    expect(s).toMatchObject({ isAnalyzingRoute: true, error: null, routeAnalysisJobId: null })

    s = reducer(s, { type: actions.analyzeRoute.fulfilled.type, payload: 'job-2' })
    expect(s).toMatchObject({ isAnalyzingRoute: true, routeAnalysisJobId: 'job-2' })

    s = reducer(s, actions.finishAnalysis())
    expect(s.isAnalyzingRoute).toBe(false)
  })

  it('surfaces a failed start', () => {
    const busy: MapState = { ...initialState, isAnalyzingRoute: true }
    expect(reducer(busy, rejected(actions.analyzeRoute.rejected.type, { message: 'quota' }))).toMatchObject({
      isAnalyzingRoute: false,
      error: 'quota',
    })
    expect(reducer(busy, rejected(actions.analyzeRoute.rejected.type, {})).error).toBe('Analysis start failed')
  })

  it('re-attaches to a job that is still running after a reload', () => {
    const s = reducer(initialState, actions.restoreRouteJob('job-9'))
    expect(s).toMatchObject({ routeAnalysisJobId: 'job-9', isAnalyzingRoute: true })
  })
})
