import { describe, it, expect } from 'vitest'
import { RQI_MODEL_LEVELS, RQI_UNKNOWN, fromSeverity as sv, rqiLevel, rqiValue } from '../../ui'
import type { RqiLevelKey } from '../../ui'
import { rqiClassColor, summarizeRouteQuality, weightedMeanRqi } from './routeSummary'
import type { RouteQuality } from './types'

// RQI values as sv(severity) (1 = best) or level keys, so the expectations hold
// for either numbering of the canonical scale. lengthByRqi is best first.
const colorOf = (key: RqiLevelKey) => rqiLevel(rqiValue(key))!.color

const quality = (over: Partial<RouteQuality> = {}): RouteQuality => ({
  totalLengthM: 10000,
  coveredLengthM: 6000,
  lengthByRqi: [3000, 1500, 1000, 500],
  meanScore: null,
  worstSegments: [],
  ...over,
})

describe('weightedMeanRqi', () => {
  it('weights each class by its length', () => {
    // severity: (3000*1 + 1500*2 + 1000*3 + 500*4) / 6000 = 11000 / 6000
    expect(weightedMeanRqi([3000, 1500, 1000, 500])).toBeCloseTo(sv(1.8333), 3)
    expect(weightedMeanRqi([0, 0, 0, 250])).toBe(sv(4))
  })

  it('is null without any measured length and ignores junk values', () => {
    expect(weightedMeanRqi([0, 0, 0, 0])).toBeNull()
    expect(weightedMeanRqi([])).toBeNull()
    expect(weightedMeanRqi([NaN, -5, 100, 0])).toBe(sv(3))
  })
})

describe('summarizeRouteQuality', () => {
  it('computes coverage and the shares of the whole route', () => {
    const s = summarizeRouteQuality(quality())
    expect(s.coverage).toBeCloseTo(0.6)
    expect(s.hasData).toBe(true)
    expect(s.lowCoverage).toBe(false)
    expect(s.classes.map(c => c.rqi)).toEqual([...RQI_MODEL_LEVELS])
    expect(s.classes.map(c => c.rqi)).toEqual([1, 2, 3, 4].map(sv))
    expect(s.classes.map(c => c.share)).toEqual([0.3, 0.15, 0.1, 0.05])
    expect(s.unknownShare).toBeCloseTo(0.4)
  })

  it('labels and colours each class from the shared RQI helpers', () => {
    const s = summarizeRouteQuality(quality())
    expect(s.classes.map(c => c.label)).toEqual(['Kiváló', 'Jó', 'Közepes', 'Rossz'])
    expect(s.classes.map(c => c.color)).toEqual(
      (['excellent', 'good', 'fair', 'poor'] as const).map(colorOf),
    )
    expect(new Set(s.classes.map(c => c.color)).size).toBe(4) // every class distinct
  })

  it('falls back to the length-weighted class mean when the API gives none', () => {
    const s = summarizeRouteQuality(quality())
    expect(s.meanScore).toBeCloseTo(sv(1.8333), 3)
    expect(s.meanLabel).toBe('Jó')
  })

  it('prefers the mean score sent by the API', () => {
    const s = summarizeRouteQuality(quality({ meanScore: sv(2.7) }))
    expect(s.meanScore).toBe(sv(2.7))
    expect(s.meanLabel).toBe('Közepes')
  })

  it('colours the mean by the class its label names', () => {
    // Jó + 0.4 toward worse is still "Jó" (nearest level), although
    // getRQIColor alone rounds it to Közepes.
    expect(summarizeRouteQuality(quality({ meanScore: sv(2.4) }))).toMatchObject({
      meanLabel: 'Jó',
      meanColor: colorOf('good'),
    })
    expect(rqiClassColor(sv(1.5))).toBe(colorOf('excellent'))
    expect(rqiClassColor(sv(2.5))).toBe(colorOf('good')) // Jó (edge toward worse)
    expect(rqiClassColor(sv(2.6))).toBe(colorOf('fair'))
    expect(rqiClassColor(sv(3.5))).toBe(colorOf('fair'))
    expect(rqiClassColor(sv(3.6))).toBe(colorOf('poor'))
    expect(rqiClassColor(null)).toBe(RQI_UNKNOWN.color)
  })

  it('reports "no data" when nothing on the route is measured', () => {
    const s = summarizeRouteQuality(
      quality({ coveredLengthM: 0, lengthByRqi: [0, 0, 0, 0], meanScore: null }),
    )
    expect(s.hasData).toBe(false)
    expect(s.coverage).toBe(0)
    expect(s.meanScore).toBeNull()
    expect(s.meanLabel).toBe('Nincs adat')
    expect(s.unknownShare).toBe(1)
    expect(s.lowCoverage).toBe(false)
  })

  it('ignores a mean score when there is no coverage behind it', () => {
    const s = summarizeRouteQuality(
      quality({ coveredLengthM: 0, lengthByRqi: [0, 0, 0, 0], meanScore: sv(2) }),
    )
    expect(s.meanScore).toBeNull()
  })

  it('flags a thinly covered route', () => {
    const s = summarizeRouteQuality(quality({ coveredLengthM: 1000, lengthByRqi: [0, 1000, 0, 0] }))
    expect(s.coverage).toBeCloseTo(0.1)
    expect(s.lowCoverage).toBe(true)
  })

  it('survives an empty route and a malformed payload', () => {
    const empty = summarizeRouteQuality(
      quality({ totalLengthM: 0, coveredLengthM: 0, lengthByRqi: [] }),
    )
    expect(empty.hasData).toBe(false)
    expect(empty.classes).toHaveLength(4)
    expect(empty.classes.every(c => c.share === 0)).toBe(true)

    const short = summarizeRouteQuality(quality({ lengthByRqi: [6000] }))
    expect(short.classes.map(c => c.lengthM)).toEqual([6000, 0, 0, 0])
  })

  it('never reports more than the whole route as covered', () => {
    const s = summarizeRouteQuality(
      quality({ totalLengthM: 1000, coveredLengthM: 1200, lengthByRqi: [600, 600, 0, 0] }),
    )
    expect(s.coverage).toBe(1)
    expect(s.classes[0].share + s.classes[1].share).toBeCloseTo(1)
    expect(s.unknownShare).toBeCloseTo(0)
  })

  it('counts covered-but-unrated length as covered, not as a class', () => {
    // 6 km covered, only 4 km of it rated.
    const s = summarizeRouteQuality(quality({ lengthByRqi: [2000, 2000, 0, 0] }))
    expect(s.coverage).toBeCloseTo(0.6)
    expect(s.classes[0].share + s.classes[1].share).toBeCloseTo(0.4)
    expect(s.unknownShare).toBeCloseTo(0.6)
  })
})
