import { describe, it, expect } from 'vitest'
import { RQI_MODEL_LEVELS } from '../../ui'
import reducer, { actions, initialState } from './slice'
import { actions as mapActions } from '../slice'
import { isUnknownFieldError } from './api'
import { mockRoadSegments, mockRouteQuality } from './mock'
import { summarizeRouteQuality } from './routeSummary'
import type { RoadSegment, RouteQuality } from './types'

const segment = (id: string): RoadSegment => ({
  id,
  path: [
    [47.5, 19.04],
    [47.501, 19.042],
  ],
  rqi: 3,
  score: 3.1,
  pBad: 0.4,
  confidence: 0.6,
  confidenceLevel: 'medium',
  nImages: 6,
  lengthM: 190,
  roadName: null,
  highway: 'residential',
  captureDateMin: null,
  captureDateMax: null,
})

const routeQuality: RouteQuality = {
  totalLengthM: 1000,
  coveredLengthM: 400,
  lengthByRqi: [400, 0, 0, 0],
  meanScore: 1.2,
  worstSegments: [],
}

const pendingMeta = (requestId: string, arg: unknown) => ({
  requestId,
  arg,
  requestStatus: 'pending' as const,
})

describe('roads slice — viewport segments', () => {
  const query = { bbox: [19, 47, 19.1, 47.1], zoom: 14 }

  it('refreshes the selected same-id segment from the new list and retains an offscreen selection', () => {
    const fresh = { ...segment('s1'), confidence: 0.95, roadName: 'Friss utca' }
    let state = reducer(initialState, actions.selectSegment(segment('s1')))
    state = reducer(state, { type: actions.fetchSegments.pending.type, meta: pendingMeta('a', query) })
    state = reducer(state, { type: actions.fetchSegments.fulfilled.type, payload: [fresh], meta: { requestId: 'a' } })
    expect(state.selected).toBe(state.items[0])
    expect(state.selected).toEqual(fresh)
    state = reducer(state, { type: actions.fetchSegments.fulfilled.type, payload: [], meta: { requestId: 'a' } })
    expect(state.selected).toEqual(fresh)
  })

  it('stores the result of the latest request and remembers the query', () => {
    let state = reducer(initialState, { type: actions.fetchSegments.pending.type, meta: pendingMeta('a', query) })
    expect(state.loading).toBe(true)
    expect(state.lastQuery).toEqual(query)

    state = reducer(state, {
      type: actions.fetchSegments.fulfilled.type,
      payload: [segment('s1')],
      meta: { requestId: 'a', arg: query },
    })
    expect(state.loading).toBe(false)
    expect(state.items.map(s => s.id)).toEqual(['s1'])
  })

  it('ignores the late outcome of a superseded request', () => {
    let state = reducer(initialState, { type: actions.fetchSegments.pending.type, meta: pendingMeta('a', query) })
    state = reducer(state, { type: actions.fetchSegments.pending.type, meta: pendingMeta('b', query) })

    // The aborted first request reports back after the second one started.
    state = reducer(state, {
      type: actions.fetchSegments.rejected.type,
      error: { message: 'Aborted' },
      meta: { requestId: 'a', arg: query },
    })
    expect(state.loading).toBe(true)
    expect(state.error).toBeNull()
  })

  it('keeps an abort silent but reports a real failure', () => {
    let state = reducer(initialState, { type: actions.fetchSegments.pending.type, meta: pendingMeta('a', query) })
    state = reducer(state, {
      type: actions.fetchSegments.rejected.type,
      error: { message: 'Network down' },
      meta: { requestId: 'a', arg: query },
    })
    expect(state.loading).toBe(false)
    expect(state.error).toBe('Network down')
  })

  it('markUnsupported switches the layer off for good', () => {
    const state = reducer({ ...initialState, items: [segment('s1')], selected: segment('s1') }, actions.markUnsupported())
    expect(state.supported).toBe(false)
    expect(state.items).toEqual([])
    expect(state.selected).toBeNull()
  })
})

describe('roads slice — selection', () => {
  it('selects and clears a segment', () => {
    let state = reducer(initialState, actions.selectSegment(segment('s1')))
    expect(state.selected?.id).toBe('s1')
    state = reducer(state, actions.selectSegment(null))
    expect(state.selected).toBeNull()
  })

  it('focusSegment selects and requests a map fit, counting up each time', () => {
    let state = reducer(initialState, actions.focusSegment(segment('s1')))
    expect(state.selected?.id).toBe('s1')
    expect(state.focus).toEqual({
      bounds: [
        [47.5, 19.04],
        [47.501, 19.042],
      ],
      seq: 1,
    })
    state = reducer(state, actions.focusSegment(segment('s1')))
    expect(state.focus?.seq).toBe(2) // clicking the same segment again re-fits
  })

  it('keeps frames only for the segment that is still selected', () => {
    const frames = [{ id: 1, latitude: 47.5, longitude: 19.04 }]
    let state = reducer(initialState, actions.selectSegment(segment('s1')))
    state = reducer(state, {
      type: actions.fetchSegmentFrames.fulfilled.type,
      payload: frames,
      meta: { requestId: 'f', arg: segment('s1') },
    })
    expect(state.frames).toEqual(frames)

    // Selecting another segment drops the old frames; a late answer for the
    // old one is ignored.
    state = reducer(state, actions.selectSegment(segment('s2')))
    expect(state.frames).toEqual([])
    state = reducer(state, {
      type: actions.fetchSegmentFrames.fulfilled.type,
      payload: frames,
      meta: { requestId: 'f', arg: segment('s1') },
    })
    expect(state.frames).toEqual([])
  })

  it('clears the selection when a route location is being picked', () => {
    let state = reducer(initialState, actions.selectSegment(segment('s1')))
    state = reducer(state, mapActions.startPickingLocation('origin'))
    expect(state.selected).toBeNull()
  })
})

describe('roads slice — route quality', () => {
  const path = [
    [47.5, 19.04],
    [47.6, 19.1],
  ]

  it('loads the summary', () => {
    let state = reducer(initialState, { type: actions.fetchRouteQuality.pending.type, meta: pendingMeta('q', path) })
    expect(state.routeQualityLoading).toBe(true)
    state = reducer(state, {
      type: actions.fetchRouteQuality.fulfilled.type,
      payload: routeQuality,
      meta: { requestId: 'q', arg: path },
    })
    expect(state.routeQualityLoading).toBe(false)
    expect(state.routeQuality).toEqual(routeQuality)
  })

  it('reports a failure', () => {
    let state = reducer(initialState, { type: actions.fetchRouteQuality.pending.type, meta: pendingMeta('q', path) })
    state = reducer(state, {
      type: actions.fetchRouteQuality.rejected.type,
      error: { message: 'boom' },
      meta: { requestId: 'q', arg: path },
    })
    expect(state.routeQualityLoading).toBe(false)
    expect(state.routeQualityError).toBe('boom')
  })

  it('drops the summary when the route is cleared or re-planned', () => {
    const loaded = { ...initialState, routeQuality }
    expect(reducer(loaded, mapActions.clearRoute()).routeQuality).toBeNull()
    expect(
      reducer(loaded, { type: mapActions.planRoute.pending.type, meta: pendingMeta('p', {}) }).routeQuality,
    ).toBeNull()
  })

  it('ignores a summary that arrives after the route was cleared', () => {
    let state = reducer(initialState, { type: actions.fetchRouteQuality.pending.type, meta: pendingMeta('q', path) })
    state = reducer(state, mapActions.clearRoute())
    state = reducer(state, {
      type: actions.fetchRouteQuality.fulfilled.type,
      payload: routeQuality,
      meta: { requestId: 'q', arg: path },
    })
    expect(state.routeQuality).toBeNull()
  })
})

describe('isUnknownFieldError', () => {
  it('recognises GraphQL validation errors for the given field', () => {
    expect(isUnknownFieldError(new Error("Cannot query field 'roadSegments' on type 'Query'."), 'roadSegments')).toBe(true)
    expect(
      isUnknownFieldError({ errors: [{ message: 'Cannot query field "routeQuality" on type "Query".' }] }, 'routeQuality'),
    ).toBe(true)
    expect(
      isUnknownFieldError(
        { message: 'Response not successful', bodyText: '{"errors":[{"message":"Cannot query field \'roadSegments\'"}]}' },
        'roadSegments',
      ),
    ).toBe(true)
  })

  it('does not match other errors or other fields', () => {
    expect(isUnknownFieldError(new Error('Network down'), 'roadSegments')).toBe(false)
    expect(isUnknownFieldError(new Error("Cannot query field 'foo' on type 'Query'."), 'roadSegments')).toBe(false)
    expect(isUnknownFieldError(null, 'roadSegments')).toBe(false)
  })
})

// The mock stands in for the backend during visual checks: keep it honest to
// the contract so the UI is exercised with realistic payloads.
describe('mock data follows the API contract', () => {
  const bbox = [19.03, 47.49, 19.07, 47.51]

  it('returns nothing below the segment zoom, like the API', () => {
    expect(mockRoadSegments(bbox, 12)).toEqual([])
  })

  it('returns well-formed, stable segments', () => {
    const segments = mockRoadSegments(bbox, 14)
    expect(segments.length).toBeGreaterThan(20)
    expect(mockRoadSegments(bbox, 14)).toEqual(segments) // deterministic
    for (const s of segments) {
      expect(s.path.length).toBeGreaterThanOrEqual(2)
      expect(RQI_MODEL_LEVELS).toContain(s.rqi)
      expect(s.confidence).toBeGreaterThanOrEqual(0)
      expect(s.confidence).toBeLessThanOrEqual(1)
      expect(['high', 'medium', 'low']).toContain(s.confidenceLevel)
      expect(s.captureDateMin! <= s.captureDateMax!).toBe(true)
    }
    expect(new Set(segments.map(s => s.id)).size).toBe(segments.length)
  })

  it('produces a route summary the card can digest', () => {
    const path: [number, number][] = Array.from({ length: 60 }, (_, i) => [47.5 + i * 0.002, 19.04 + i * 0.001])
    const quality = mockRouteQuality(path)
    const summary = summarizeRouteQuality(quality)
    expect(quality.lengthByRqi).toHaveLength(4)
    expect(summary.coverage).toBeGreaterThan(0)
    expect(summary.coverage).toBeLessThanOrEqual(1)
    expect(quality.worstSegments.length).toBeLessThanOrEqual(5)
  })
})
