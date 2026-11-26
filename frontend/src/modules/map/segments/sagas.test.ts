import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { runSaga } from 'redux-saga'
import type { SagaPendingAction } from 'saga-toolkit'
import type { RoadSegment } from './types'

// The network layer is replaced: gqlQuery hands back whatever the test queued.
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
  onRoutePlanned,
  onSegmentSelected,
} from './sagas'
import { actions, fetchRouteQuality, fetchSegmentFrames, fetchSegments } from './slice'
import { actions as mapActions } from '../slice'

const segment = (over: Partial<RoadSegment> = {}): RoadSegment => ({
  id: 'seg-1',
  path: [
    [47.5, 19.04],
    [47.501, 19.04],
  ],
  rqi: 2,
  score: 2.1,
  pBad: 0.1,
  confidence: 0.9,
  confidenceLevel: 'high',
  nImages: 10,
  lengthM: 111,
  roadName: 'Váci út',
  highway: 'primary',
  captureDateMin: '2023-05',
  captureDateMax: '2025-08',
  ...over,
})

const pending = <T>(arg: unknown) => ({ type: 'test/pending', meta: { arg, requestId: 'r1' } }) as T

// Runs a worker outside the store; collects what it dispatches.
const run = (saga: unknown, action: unknown) => {
  const dispatched: unknown[] = []
  const task = runSaga(
    { dispatch: (a: unknown) => void dispatched.push(a), getState: () => ({}) },
    saga as (action: unknown) => Generator,
    action,
  )
  return { task, dispatched }
}

const BBOX = [19.0, 47.4, 19.1, 47.6]

describe('fetchSegmentsWorker', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    gqlQueryMock.mockReset()
  })
  afterEach(() => vi.useRealTimers())

  const action = pending<SagaPendingAction<typeof fetchSegments>>({ bbox: BBOX, zoom: 14 })

  it('waits out the debounce, then queries with the viewport bbox and zoom', async () => {
    gqlQueryMock.mockReturnValue({ roadSegments: [segment()] })
    const { task } = run(fetchSegmentsWorker, action)

    await vi.advanceTimersByTimeAsync(SEGMENT_FETCH_DEBOUNCE_MS - 1)
    expect(gqlQueryMock).not.toHaveBeenCalled()

    await vi.advanceTimersByTimeAsync(1)
    await expect(task.toPromise()).resolves.toEqual([segment()])
    expect(gqlQueryMock).toHaveBeenCalledTimes(1)
    expect(gqlQueryMock.mock.calls[0][0].variables).toEqual({ bbox: BBOX, zoom: 14 })
  })

  it('never reaches the network when cancelled during the debounce (map moved on)', async () => {
    const { task } = run(fetchSegmentsWorker, action)
    await vi.advanceTimersByTimeAsync(100)
    task.cancel()
    await vi.advanceTimersByTimeAsync(1000)
    expect(gqlQueryMock).not.toHaveBeenCalled()
  })

  it('falls back to the legacy view when the backend has no roadSegments', async () => {
    gqlQueryMock.mockImplementation(() => {
      throw new Error("Cannot query field 'roadSegments' on type 'Query'.")
    })
    const { task, dispatched } = run(fetchSegmentsWorker, action)
    await vi.advanceTimersByTimeAsync(SEGMENT_FETCH_DEBOUNCE_MS)

    await expect(task.toPromise()).resolves.toEqual([])
    expect(dispatched[0]).toEqual(actions.markUnsupported())
    // + the legacy fetch for this viewport (zoom 14 → points), a thunk.
    expect(dispatched).toHaveLength(2)
    expect(typeof dispatched[1]).toBe('function')
  })

  it('lets any other error fail the request', async () => {
    gqlQueryMock.mockImplementation(() => {
      throw new Error('Network down')
    })
    const { task, dispatched } = run(fetchSegmentsWorker, action)
    const outcome = expect(task.toPromise()).rejects.toThrow('Network down')
    await vi.advanceTimersByTimeAsync(SEGMENT_FETCH_DEBOUNCE_MS)
    await outcome
    expect(dispatched).toHaveLength(0)
  })
})

describe('fetchSegmentFramesWorker', () => {
  // Braces matter: a function RETURNED from beforeEach would run as teardown.
  beforeEach(() => {
    gqlQueryMock.mockReset()
  })

  it('keeps only the frames lying on the segment', async () => {
    gqlQueryMock.mockReturnValue({
      points: [
        { id: 1, latitude: 47.5005, longitude: 19.04, rqiScore: 2, captureDate: '2024-01' },
        // ~75 m east of the segment: inside the bbox query, but another road.
        { id: 2, latitude: 47.5005, longitude: 19.041, rqiScore: 4, captureDate: null },
      ],
    })
    const { task } = run(
      fetchSegmentFramesWorker,
      pending<SagaPendingAction<typeof fetchSegmentFrames>>(segment()),
    )
    const frames = (await task.toPromise()) as Array<{ id: number }>
    expect(frames.map(f => f.id)).toEqual([1])
    expect(frames[0]).toMatchObject({ latitude: 47.5005, rqi_score: 2, capture_date: '2024-01' })

    const { bbox, limit } = gqlQueryMock.mock.calls[0][0].variables
    expect(limit).toBeGreaterThan(0)
    expect(bbox[0]).toBeLessThan(19.04) // padded around the path
    expect(bbox[3]).toBeGreaterThan(47.501)
  })

  it('returns no frames (instead of failing) when the query errors', async () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {})
    gqlQueryMock.mockImplementation(() => {
      throw new Error('boom')
    })
    const { task } = run(
      fetchSegmentFramesWorker,
      pending<SagaPendingAction<typeof fetchSegmentFrames>>(segment()),
    )
    await expect(task.toPromise()).resolves.toEqual([])
    warn.mockRestore()
  })
})

describe('fetchRouteQualityWorker', () => {
  // Braces matter: a function RETURNED from beforeEach would run as teardown.
  beforeEach(() => {
    gqlQueryMock.mockReset()
  })

  const path: [number, number][] = [
    [47.5, 19.04],
    [47.6, 19.1],
  ]
  const action = pending<SagaPendingAction<typeof fetchRouteQuality>>(path)

  it('sends the planned path as it is and returns the summary', async () => {
    const routeQuality = {
      totalLengthM: 1000,
      coveredLengthM: 500,
      lengthByRqi: [500, 0, 0, 0],
      meanScore: 1,
      worstSegments: [],
    }
    gqlQueryMock.mockReturnValue({ routeQuality })
    const { task } = run(fetchRouteQualityWorker, action)
    await expect(task.toPromise()).resolves.toEqual(routeQuality)
    expect(gqlQueryMock.mock.calls[0][0].variables).toEqual({ path })
  })

  it('resolves to null when the backend has no routeQuality yet', async () => {
    gqlQueryMock.mockImplementation(() => {
      throw new Error('Cannot query field "routeQuality" on type "Query".')
    })
    const { task } = run(fetchRouteQualityWorker, action)
    await expect(task.toPromise()).resolves.toBeNull()
  })
})

describe('reactions', () => {
  it('asks for the route quality as soon as a route is planned', () => {
    const { dispatched } = run(onRoutePlanned, {
      type: mapActions.planRoute.fulfilled.type,
      payload: [
        [47.5, 19.04],
        [47.6, 19.1],
      ],
    })
    expect(dispatched).toHaveLength(1)
    expect(typeof dispatched[0]).toBe('function') // fetchRouteQuality thunk
  })

  it('does not ask for an empty route', () => {
    const { dispatched } = run(onRoutePlanned, {
      type: mapActions.planRoute.fulfilled.type,
      payload: [],
    })
    expect(dispatched).toHaveLength(0)
  })

  it('selecting a segment closes the point card and loads its frames', () => {
    const { dispatched } = run(onSegmentSelected, actions.selectSegment(segment()))
    expect(dispatched[0]).toEqual(mapActions.selectPoint(null))
    expect(typeof dispatched[1]).toBe('function') // fetchSegmentFrames thunk
  })

  it('clearing the selection does nothing else', () => {
    const { dispatched } = run(onSegmentSelected, actions.selectSegment(null))
    expect(dispatched).toHaveLength(0)
  })
})
