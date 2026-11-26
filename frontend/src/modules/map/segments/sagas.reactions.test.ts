import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { runSaga } from 'redux-saga'
import type { SagaPendingAction } from 'saga-toolkit'
import type { LatLng, RoadSegment } from './types'

// Same network stand-in as sagas.test.ts: gqlQuery returns what the test queued.
const gqlQueryMock = vi.hoisted(() => vi.fn())
vi.mock('../../graphql', () => ({
  gql: (source: string) => ({ kind: 'Document', source }),
  // eslint-disable-next-line require-yield
  gqlQuery: function* (options: unknown) {
    return gqlQueryMock(options)
  },
}))

import {
  SEGMENT_FETCH_DEBOUNCE_MS,
  fetchRouteQualityWorker,
  fetchSegmentFramesWorker,
  fetchSegmentsWorker,
  onAnalysisFinished,
  onRouteAlternativeSelected,
} from './sagas'
import { fetchRouteQuality, fetchSegmentFrames, fetchSegments, initialState as roadsInitial } from './slice'
import { initialState as mapInitial } from '../slice'
import { mockRoadSegments, mockRouteQuality } from './mock'

const ROUTE: LatLng[] = [
  [47.5, 19.04],
  [47.6, 19.1],
]
const QUERY = { bbox: [19.0, 47.4, 19.1, 47.6], zoom: 14 }

const pending = <T>(arg: unknown) => ({ type: 'test/pending', meta: { arg, requestId: 'r1' } }) as T

interface StateOver {
  zoom?: number
  route?: LatLng[] | null
  supported?: boolean
  lastQuery?: { bbox: number[]; zoom: number } | null
}

const stateWith = ({ zoom = 14, route = null, supported = true, lastQuery = null }: StateOver = {}) => ({
  map: { ...mapInitial, viewport: { ...mapInitial.viewport, zoom }, routePoints: route },
  roads: { ...roadsInitial, supported, lastQuery },
})

// Runs a saga outside the store; collects what it dispatches.
const run = (saga: unknown, state: object = {}, action?: unknown) => {
  const dispatched: unknown[] = []
  const task = runSaga(
    { dispatch: (a: unknown) => void dispatched.push(a), getState: () => state },
    saga as (action: unknown) => Generator,
    action,
  )
  return { task, dispatched }
}

/** The `pending` action a dispatched saga-action thunk announces itself with. */
const announced = (thunk: unknown): { type: string; arg: unknown } => {
  expect(typeof thunk).toBe('function')
  const seen: { type: string; meta?: { arg?: unknown } }[] = []
  void (thunk as (dispatch: (a: never) => void, getState: () => object, extra: undefined) => unknown)(
    a => void seen.push(a),
    () => ({}),
    undefined,
  )
  return { type: seen[0]?.type, arg: seen[0]?.meta?.arg }
}

describe('onRouteAlternativeSelected', () => {
  it('fetches the quality summary of the newly drawn alternative', () => {
    const { dispatched } = run(onRouteAlternativeSelected, stateWith({ route: ROUTE }))
    expect(dispatched).toHaveLength(1)
    expect(announced(dispatched[0])).toEqual({ type: fetchRouteQuality.pending.type, arg: ROUTE })
  })

  it('does nothing without a drawable route', () => {
    expect(run(onRouteAlternativeSelected, stateWith({ route: null })).dispatched).toHaveLength(0)
    expect(run(onRouteAlternativeSelected, stateWith({ route: [ROUTE[0]] })).dispatched).toHaveLength(0)
  })
})

describe('onAnalysisFinished', () => {
  it('refreshes the visible segments and the route summary', () => {
    const { dispatched } = run(onAnalysisFinished, stateWith({ zoom: 14, route: ROUTE, lastQuery: QUERY }))
    expect(dispatched.map(announced)).toEqual([
      { type: fetchSegments.pending.type, arg: QUERY },
      { type: fetchRouteQuality.pending.type, arg: ROUTE },
    ])
  })

  it('skips the segments while the zoomed-out grid is showing', () => {
    const { dispatched } = run(onAnalysisFinished, stateWith({ zoom: 10, route: ROUTE, lastQuery: QUERY }))
    expect(dispatched.map(announced)).toEqual([{ type: fetchRouteQuality.pending.type, arg: ROUTE }])
  })

  it('skips the segments when the viewport was never queried', () => {
    const { dispatched } = run(onAnalysisFinished, stateWith({ zoom: 15, route: null, lastQuery: null }))
    expect(dispatched).toHaveLength(0)
  })

  it('asks nothing of a backend without the segment API', () => {
    const { dispatched } = run(
      onAnalysisFinished,
      stateWith({ zoom: 15, route: ROUTE, lastQuery: QUERY, supported: false }),
    )
    expect(dispatched).toHaveLength(0)
  })
})

describe('workers — edge cases', () => {
  beforeEach(() => {
    gqlQueryMock.mockReset()
  })

  it('a segment without geometry has no frames and needs no request', async () => {
    const empty = { id: 's0', path: [] } as unknown as RoadSegment
    const { task } = run(fetchSegmentFramesWorker, {}, pending<SagaPendingAction<typeof fetchSegmentFrames>>(empty))
    await expect(task.toPromise()).resolves.toEqual([])
    expect(gqlQueryMock).not.toHaveBeenCalled()
  })

  it('a route-quality failure other than "unknown field" is a real error', async () => {
    gqlQueryMock.mockImplementation(() => {
      throw new Error('Internal server error')
    })
    const { task } = run(fetchRouteQualityWorker, {}, pending<SagaPendingAction<typeof fetchRouteQuality>>(ROUTE))
    await expect(task.toPromise()).rejects.toThrow('Internal server error')
  })
})

describe('workers — mock mode (VITE_MOCK_SEGMENTS=1)', () => {
  beforeEach(() => {
    gqlQueryMock.mockReset()
    vi.stubEnv('VITE_MOCK_SEGMENTS', '1')
  })
  afterEach(() => {
    vi.unstubAllEnvs()
    vi.useRealTimers()
  })

  it('serves the route summary from the mock module, never the network', async () => {
    const { task } = run(fetchRouteQualityWorker, {}, pending<SagaPendingAction<typeof fetchRouteQuality>>(ROUTE))
    await expect(task.toPromise()).resolves.toEqual(mockRouteQuality(ROUTE))
    expect(gqlQueryMock).not.toHaveBeenCalled()
  })

  it('serves the viewport segments from the mock module after the debounce', async () => {
    vi.useFakeTimers()
    const { task } = run(fetchSegmentsWorker, {}, pending<SagaPendingAction<typeof fetchSegments>>(QUERY))
    await vi.advanceTimersByTimeAsync(SEGMENT_FETCH_DEBOUNCE_MS)
    vi.useRealTimers()
    await expect(task.toPromise()).resolves.toEqual(mockRoadSegments(QUERY.bbox, QUERY.zoom))
    expect(gqlQueryMock).not.toHaveBeenCalled()
  })
})
