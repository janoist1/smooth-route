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
import reducer, { actions } from './slice'

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
      })),
    },
  },
}
const endpoints = { origin: 'Budapest', destination: 'Budaörs' }
const setup = () => {
  const middleware = createSagaMiddleware()
  const store = configureStore({
    reducer: combineReducers({ map: reducer }),
    middleware: gdm => gdm({ serializableCheck: false }).concat(middleware),
  })
  const task = middleware.run(function* () { yield all(sagas) })
  return { store, task }
}

afterEach(() => vi.resetAllMocks())

describe('route planning and analysis', () => {
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
