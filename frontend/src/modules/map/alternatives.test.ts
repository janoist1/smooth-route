import { describe, expect, it } from 'vitest'
import reducer, { actions } from './slice'
import { defaultRouteIndex, extraDurationLabel, formatDuration, type RouteAlternative } from './alternatives'

const quality = { totalLengthM: 1000, coveredLengthM: 800, lengthByRqi: [800, 0, 0, 0], meanScore: 4, worstSegments: [] }
const route = (index: number, durationS: number, extra: Partial<RouteAlternative> = {}): RouteAlternative => ({
  index,
  points: [[47.5, 19 + index * 0.01], [47.49, 19.05]],
  distanceM: 5000,
  durationS,
  summary: `R${index}`,
  quality,
  coverage: 0.8,
  isFastest: false,
  isSmoothest: false,
  ...extra,
})

describe('route alternatives helpers', () => {
  it('shows the smoothest first, else the fastest, else Google’s first', () => {
    const routes = [route(0, 600), route(1, 650)]
    expect(defaultRouteIndex({ routes, fastestIndex: 0, smoothestIndex: 1 })).toBe(1)
    expect(defaultRouteIndex({ routes, fastestIndex: 0, smoothestIndex: null })).toBe(0)
    expect(defaultRouteIndex({ routes, fastestIndex: null, smoothestIndex: null })).toBe(0)
    expect(defaultRouteIndex({ routes: [], fastestIndex: null, smoothestIndex: null })).toBeNull()
  })

  it('formats durations and the extra time against the fastest', () => {
    expect(formatDuration(30)).toBe('1 perc')
    expect(formatDuration(23 * 60)).toBe('23 perc')
    expect(formatDuration(65 * 60)).toBe('1 ó 05 perc')
    const fast = route(0, 600)
    expect(extraDurationLabel(route(1, 840), fast)).toBe('+4 perc')
    expect(extraDurationLabel(fast, fast)).toBe('')
  })
})

describe('map slice: alternatives', () => {
  it('selecting an alternative swaps the drawn route; clearing forgets them', () => {
    const routes = [route(0, 600), route(1, 650)]
    let s = reducer(undefined, actions.setRouteAlternatives({ routes, selected: 1 }))
    expect(s.selectedRouteIndex).toBe(1)
    s = reducer(s, actions.selectRouteAlternative(0))
    expect(s.selectedRouteIndex).toBe(0)
    expect(s.routePoints).toEqual(routes[0].points)
    s = reducer(s, actions.selectRouteAlternative(7)) // unknown: ignored
    expect(s.selectedRouteIndex).toBe(0)
    s = reducer(s, actions.clearRoute())
    expect(s.routeAlternatives).toBeNull()
    expect(s.routePoints).toBeNull()
  })
})
