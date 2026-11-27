import { afterEach, describe, expect, it, vi } from 'vitest'
import { combineReducers, configureStore } from '@reduxjs/toolkit'
import createSagaMiddleware from 'redux-saga'
import type { SagaIterator } from 'redux-saga'
import { all, call } from 'redux-saga/effects'

const { query, mutate } = vi.hoisted(() => ({ query: vi.fn(), mutate: vi.fn() }))
vi.mock('../graphql', () => ({
  gql: (source: string) => source,
  *gqlQueryResult(options: unknown): SagaIterator { return yield call(query, options) },
  *gqlQuery(options: unknown): SagaIterator { return yield call(query, options) },
  *gqlMutate(options: unknown): SagaIterator { return yield call(mutate, options) },
}))

import sagas from './sagas'
import reducer, { actions, initialState } from './slice'
import roadsReducer from './segments/slice'
import roadsSagas from './segments/sagas'
import type { RouteAlternative } from './alternatives'
import type { RouteQuality } from './segments/types'
import { RQI_MODEL_LEVELS, rqiValue } from '../ui/utils/rqiScale'

const alternatives = {
  data: {
    routeAlternatives: {
      fastestIndex: 0,
      smoothestIndex: null,
      routes: [0, 1].map(index => ({
        index,
        points: [{ lat: 47.5, lng: 19.04 }, { lat: 47.51 + index * 0.01, lng: 19.05 }],
        distanceM: 2000,
        durationS: 120 + index * 10,
        summary: `route ${index}`,
        quality: { totalLengthM: 2000, coveredLengthM: 0, lengthByRqi: [], meanScore: null },
        coverage: 0,
        isFastest: index === 0,
        isSmoothest: false,
        smoothestConfident: false,
      })),
    },
  },
}
const endpoints = { origin: 'Budapest', destination: 'Budaörs' }
const setup = (routes?: RouteAlternative[]) => {
  const middleware = createSagaMiddleware()
  const store = configureStore({
    reducer: combineReducers({ map: reducer, roads: roadsReducer }),
    preloadedState: {
      map: routes ? {
        ...initialState, routeAlternatives: routes, selectedRouteIndex: routes[0].index, routePoints: routes[0].points,
      } : initialState,
    },
    middleware: gdm => gdm({ serializableCheck: false }).concat(middleware),
  })
  const task = middleware.run(function* () { yield all([...sagas, ...(routes ? roadsSagas : [])]) })
  return { store, task }
}

afterEach(() => vi.resetAllMocks())

describe('route planning and analysis', () => {
  it.each(['osm', 'google'])('keeps the server-selected %s source when switching alternatives', async provider => {
    query.mockResolvedValue({ data: { ...alternatives.data, routingProvider: provider } })
    const { store, task } = setup()
    try {
      await store.dispatch(actions.planRoute(endpoints))
      store.dispatch(actions.selectRouteAlternative(1))
      expect(store.getState().map.routeAlternatives?.map(r => r.provider)).toEqual([provider, provider])
      expect(store.getState().map.selectedRouteIndex).toBe(1)
    } finally { task.cancel() }
  })

  it.each([false, true])('preserves smoothest confidence %s from the API when planning', async smoothestConfident => {
    const response = {
      data: {
        routeAlternatives: {
          ...alternatives.data.routeAlternatives,
          smoothestIndex: 1,
          routes: alternatives.data.routeAlternatives.routes.map(route => ({
            ...route,
            isSmoothest: route.index === 1,
            smoothestConfident: route.index === 1 && smoothestConfident,
            coverage: smoothestConfident ? 0.5 : 0.234,
          })),
        },
      },
    }
    query.mockResolvedValue(response)
    const { store, task } = setup()
    try {
      await store.dispatch(actions.planRoute(endpoints))
      expect(query).toHaveBeenCalledWith(expect.objectContaining({ query: expect.stringContaining('smoothestConfident') }))
      expect(store.getState().map.routeAlternatives?.[1]).toMatchObject({ isSmoothest: true, smoothestConfident })
      // An uncertain "Legsimább?" winner is badged but not preselected.
      expect(store.getState().map.selectedRouteIndex).toBe(
        smoothestConfident ? 1 : alternatives.data.routeAlternatives.fastestIndex)
    } finally { task.cancel() }
  })

  it('analyzes alternative 2 after it is selected instead of sending only the endpoints', async () => {
    query.mockResolvedValue(alternatives)
    mutate.mockResolvedValue({ processRoute: { id: 'job-2' } })
    const { store, task } = setup()
    try {
      await store.dispatch(actions.planRoute(endpoints))
      store.dispatch(actions.selectRouteAlternative(1))
      await store.dispatch(actions.analyzeRoute(endpoints))
      const path = alternatives.data.routeAlternatives.routes[1].points.map(p => [p.lat, p.lng])
      expect(mutate).toHaveBeenCalledWith(expect.objectContaining({
        variables: { input: { ...endpoints, path } },
      }))
      expect(store.getState().map.routeAnalysisJobId).toBe('job-2')
    } finally { task.cancel() }
  })

  it('clearRoute cancels an in-flight plan and ignores its late alternatives', async () => {
    let finish!: (value: typeof alternatives) => void
    query.mockReturnValue(new Promise(resolve => { finish = resolve }))
    const { store, task } = setup()
    try {
      const pending = store.dispatch(actions.planRoute(endpoints))
      await Promise.resolve()
      expect(query).toHaveBeenCalledTimes(1)
      store.dispatch(actions.clearRoute())
      finish(alternatives)
      await pending
      expect(store.getState().map).toMatchObject({
        isPlanningRoute: false, routePoints: null, routeAlternatives: null, selectedRouteIndex: null, error: null,
      })
    } finally { task.cancel() }
  })
})

describe('alternative quality after analysis', () => {
  const routes = (): RouteAlternative[] => alternatives.data.routeAlternatives.routes.map(r => ({
    ...r,
    points: r.points.map(p => [p.lat, p.lng]),
    quality: { ...r.quality, worstSegments: [], meanScore: rqiValue('poor') },
    isSmoothest: r.index === 0,
  }))
  const quality = (meanScore: number, impactScore: number): RouteQuality => ({
    totalLengthM: 2000, coveredLengthM: 2000,
    lengthByRqi: RQI_MODEL_LEVELS.map(level => level === meanScore ? 2000 : 0),
    meanScore, impactScore, worstSegments: [],
  })
  const fresh = [quality(rqiValue('good'), 1), quality(rqiValue('excellent'), 0)]

  it('finishAnalysis refreshes every stored alternative, coverage and smoothest badge without changing the selection', async () => {
    const stored = routes()
    query.mockImplementation(({ variables }) => ({
      routeQuality: fresh[stored.findIndex(r => JSON.stringify(r.points) === JSON.stringify(variables.path))],
    }))
    const { store, task } = setup(stored)
    try {
      store.dispatch(actions.finishAnalysis())
      await vi.waitFor(() => expect(store.getState().map.routeAlternatives?.[1].isSmoothest).toBe(true))
      expect(store.getState().map.routeAlternatives).toEqual(stored.map((route, index) => ({
        ...route, quality: fresh[index], coverage: 1, isSmoothest: index === 1, smoothestConfident: index === 1,
      })))
      expect(store.getState().map.selectedRouteIndex).toBe(0)
      expect(store.getState().map.routePoints).toEqual(stored[0].points)
      await vi.waitFor(() => expect(store.getState().roads.routeQuality).toEqual(fresh[0]))
      const paths = query.mock.calls.map(([options]) => options.variables.path)
      expect(paths).toHaveLength(3)
      expect(paths.filter(path => JSON.stringify(path) === JSON.stringify(stored[0].points))).toHaveLength(2)
      expect(paths.filter(path => JSON.stringify(path) === JSON.stringify(stored[1].points))).toHaveLength(1)
    } finally { task.cancel() }
  })

  it('keeps an alternative selected during the refresh', async () => {
    const stored = routes()
    let finish!: (value: { routeQuality: RouteQuality }) => void
    let deferred = false
    query.mockImplementation(({ variables }) => {
      const index = stored.findIndex(r => JSON.stringify(r.points) === JSON.stringify(variables.path))
      if (index === 1 && !deferred) {
        deferred = true
        return new Promise(resolve => { finish = resolve })
      }
      return { routeQuality: fresh[index] }
    })
    const { store, task } = setup(stored)
    try {
      store.dispatch(actions.finishAnalysis())
      await vi.waitFor(() => expect(query).toHaveBeenCalledTimes(3))
      store.dispatch(actions.selectRouteAlternative(1))
      finish({ routeQuality: fresh[1] })
      await vi.waitFor(() => expect(store.getState().map.routeAlternatives?.[1].isSmoothest).toBe(true))
      expect(store.getState().map.selectedRouteIndex).toBe(1)
      expect(store.getState().map.routePoints).toEqual(stored[1].points)
      expect(store.getState().roads.routeQuality).toEqual(fresh[1])
    } finally { task.cancel() }
  })

  it('preserves the stored alternatives on a refresh error and can retry after the next analysis', async () => {
    const stored = routes()
    let fail = true
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {})
    query.mockImplementation(({ variables }) => {
      const index = stored.findIndex(r => JSON.stringify(r.points) === JSON.stringify(variables.path))
      if (index === 1 && fail) throw new Error('Quality unavailable')
      return { routeQuality: fresh[index] }
    })
    const { store, task } = setup(stored)
    try {
      store.dispatch(actions.finishAnalysis())
      await vi.waitFor(() => expect(warn).toHaveBeenCalledWith(
        'Route alternatives could not be refreshed:', expect.any(Error),
      ))
      expect(store.getState().map.routeAlternatives).toBe(stored)
      fail = false
      store.dispatch(actions.finishAnalysis())
      await vi.waitFor(() => expect(store.getState().map.routeAlternatives?.[1].isSmoothest).toBe(true))
    } finally { task.cancel(); warn.mockRestore() }
  })

  it.each(['clear', 'new plan'] as const)('discards an in-flight refresh after %s', async change => {
    const stored = routes()
    let finish!: (value: { routeQuality: RouteQuality }) => void
    query.mockImplementation(({ variables }) => {
      if ('origin' in variables) return alternatives
      const index = stored.findIndex(r => JSON.stringify(r.points) === JSON.stringify(variables.path))
      if (index === 1) return new Promise(resolve => { finish = resolve })
      return { routeQuality: fresh[index] }
    })
    const { store, task } = setup(stored)
    try {
      store.dispatch(actions.finishAnalysis())
      await vi.waitFor(() => expect(query).toHaveBeenCalledTimes(3))
      if (change === 'clear') store.dispatch(actions.clearRoute())
      else await store.dispatch(actions.planRoute(endpoints))
      const current = store.getState().map.routeAlternatives
      finish({ routeQuality: fresh[1] })
      await new Promise(resolve => setTimeout(resolve, 0))
      expect(store.getState().map.routeAlternatives).toBe(current)
      expect(query).toHaveBeenCalledTimes(change === 'clear' ? 3 : 5)
    } finally { task.cancel() }
  })
})
