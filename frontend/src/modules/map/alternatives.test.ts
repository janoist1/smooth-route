import { describe, expect, it } from 'vitest'
import reducer, { actions } from './slice'
import { defaultRouteIndex, extraDurationLabel, formatDuration, rankRouteAlternatives, routePlanErrorMessage, type RouteAlternative } from './alternatives'
import { rqiValue } from '../ui/utils/rqiScale'

const quality = { totalLengthM: 1000, coveredLengthM: 800, lengthByRqi: [800, 0, 0, 0], meanScore: rqiValue('good'), worstSegments: [] }
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
  it('refreshes coverage and badges using impact, excluding poorly covered and slow routes', () => {
    const candidate = (index: number, durationS: number, coveredLengthM: number, impactScore: number) =>
      route(index, durationS, {
        coverage: 0,
        isSmoothest: true,
        quality: { ...quality, coveredLengthM, impactScore, meanScore: rqiValue('good') },
      })
    const ranked = rankRouteAlternatives([
      candidate(0, 600, 800, 1), candidate(1, 720, 500, 0.5),
      candidate(2, 721, 1000, 0), candidate(3, 650, 499, 0),
    ])
    expect(ranked.map(r => r.coverage)).toEqual([0.8, 0.5, 1, 0.499])
    expect(ranked.filter(r => r.isSmoothest).map(r => r.index)).toEqual([1])
    expect(ranked.filter(r => r.isFastest).map(r => r.index)).toEqual([0])
  })

  it('falls back to canonical mean scores when any measured route lacks impact', () => {
    const ranked = rankRouteAlternatives([
      route(0, 600, { quality: { ...quality, meanScore: rqiValue('poor'), impactScore: 0 } }),
      route(1, 650, { quality: { ...quality, meanScore: rqiValue('excellent'), impactScore: null } }),
    ])
    expect(ranked.filter(r => r.isSmoothest).map(r => r.index)).toEqual([1])
  })

  it('breaks equal quality by duration, then original order, and removes obsolete badges without coverage', () => {
    const ranked = rankRouteAlternatives([route(7, 650), route(4, 600), route(9, 600)])
    expect(ranked.filter(r => r.isSmoothest).map(r => r.index)).toEqual([4])
    expect(ranked.filter(r => r.isFastest).map(r => r.index)).toEqual([4])
    expect(rankRouteAlternatives([
      route(0, 600, { isSmoothest: true, quality: { ...quality, totalLengthM: 0, coveredLengthM: 0, meanScore: null } }),
    ])[0]).toMatchObject({ coverage: 0, isSmoothest: false, isFastest: true })
    expect(rankRouteAlternatives([])).toEqual([])
  })

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

describe('routePlanErrorMessage', () => {
  it('asks to sign in when the API refuses an anonymous plan', () => {
    // Apollo 4 CombinedGraphQLErrors shape for { code: UNAUTHENTICATED }.
    const error = { errors: [{ message: 'Authentication required', extensions: { code: 'UNAUTHENTICATED' } }] }
    expect(routePlanErrorMessage(error)).toBe('Az útvonaltervezéshez jelentkezz be.')
  })

  it('falls back to a plain Hungarian message (network error, no data, unknown)', () => {
    const generic = 'Az útvonaltervezés nem sikerült, próbáld újra később.'
    expect(routePlanErrorMessage(new Error('Failed to fetch'))).toBe(generic)
    expect(routePlanErrorMessage(undefined)).toBe(generic)
    expect(routePlanErrorMessage({ errors: [{ extensions: { code: 'INTERNAL' } }] })).toBe(generic)
  })
})
