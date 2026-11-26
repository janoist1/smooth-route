import { describe, expect, it, vi } from 'vitest'
import scaleJson from './rqiScale.json'
import localRaw from './rqiScale.json?raw'
import sharedRaw from '../../../../../shared/rqi_scale.json?raw'
import {
  RQI_BAD_FROM,
  RQI_LEVELS,
  RQI_MODEL_LEVELS,
  RQI_SCALE,
  compareWorstFirst,
  isBadRqi,
  nearestRqiLevel,
  rqiLevel,
  rqiScoreLabelHu,
  rqiValue,
  towardWorseRqiLevel,
} from './rqiScale'
import { getRQIColor, getRQILabel } from './rqi'

describe('canonical RQI scale definition', () => {
  it('frontend copy is byte-identical to shared/rqi_scale.json', () => {
    // On drift run: python scripts/sync_rqi_scale.py
    expect(localRaw).toBe(sharedRaw)
  })

  it('has five levels with the Hungarian UI labels, best first', () => {
    expect(RQI_LEVELS.map(l => l.label_hu)).toEqual(['Kiváló', 'Jó', 'Közepes', 'Rossz', 'Nagyon rossz'])
    expect(RQI_LEVELS.map(l => l.key)).toEqual(['excellent', 'good', 'fair', 'poor', 'very_poor'])
  })

  it('pins the current direction and model contract', () => {
    expect(RQI_SCALE.direction).toBe('lower_is_better')
    expect(RQI_LEVELS.map(l => l.value)).toEqual([1, 2, 3, 4, 5])
    expect(RQI_MODEL_LEVELS).toEqual([1, 2, 3, 4])
    expect(RQI_BAD_FROM).toBe(rqiValue('fair'))
    expect(rqiLevel(3)?.label_hu).toBe('Közepes')
    expect(rqiLevel(2.5)).toBeUndefined()
  })
})

describe('helpers', () => {
  it('bad road = at or worse than Közepes', () => {
    expect([1, 2, 2.9, 3, 4, 5].map(isBadRqi)).toEqual([false, false, false, true, true, true])
  })

  it('sorts worst first', () => {
    expect([1, 4, 2, 3].sort(compareWorstFirst)).toEqual([4, 3, 2, 1])
  })

  it('rounds continuous scores', () => {
    expect([0.2, 1.5, 1.51, 2.5, 3.5, 4.5, 4.6, 9].map(s => nearestRqiLevel(s))).toEqual([1, 1, 2, 2, 3, 4, 5, 5])
    expect([1.49, 1.5, 2.5, 4.5].map(s => nearestRqiLevel(s, 'worse'))).toEqual([1, 2, 3, 5])
    expect([0, 2, 2.01, 3, 4, 4.01, 7].map(towardWorseRqiLevel)).toEqual([1, 2, 3, 3, 4, 5, 5])
  })

  it('Hungarian score label', () => {
    expect(rqiScoreLabelHu(1)).toBe('Kiváló')
    expect(rqiScoreLabelHu(1.5)).toBe('Kiváló')
    expect(rqiScoreLabelHu(2.6)).toBe('Közepes')
    expect(rqiScoreLabelHu(4.8)).toBe('Nagyon rossz')
    expect(rqiScoreLabelHu(null)).toBe('Nincs adat')
  })
})

// The pre-centralisation implementations, verbatim, to prove no behaviour change.
const legacyColor = (score: number): string => {
  if (score <= 2.0) return '#4ade80'
  if (score <= 3.0) return '#facc15'
  if (score <= 4.0) return '#f87171'
  return '#ef4444'
}
const legacyLabel = (score: number): string => {
  if (score <= 1.5) return 'Excellent'
  if (score <= 2.5) return 'Good'
  if (score <= 3.5) return 'Fair'
  if (score <= 4.5) return 'Poor'
  return 'Critical'
}

describe('getRQIColor / getRQILabel are unchanged', () => {
  const samples: number[] = []
  for (let s = -1; s <= 7.0001; s += 0.01) samples.push(Math.round(s * 100) / 100)

  it('colour matches the legacy bands on a 0.01 grid', () => {
    for (const s of samples) expect(getRQIColor(s), `score ${s}`).toBe(legacyColor(s))
  })

  it('label matches the legacy bands on a 0.01 grid', () => {
    for (const s of samples) expect(getRQILabel(s), `score ${s}`).toBe(legacyLabel(s))
  })
})

describe('a flipped scale (5 = best) answers the same on mirrored data', () => {
  it('mirrors levels and keeps labels, colours and the bad-road decision', async () => {
    const flipped = {
      ...scaleJson,
      direction: 'higher_is_better',
      bad_from: 6 - scaleJson.bad_from,
      model_levels: scaleJson.model_levels.map(v => 6 - v).sort(),
      levels: scaleJson.levels.map(l => ({ ...l, value: 6 - l.value })),
    }
    vi.resetModules()
    vi.doMock('./rqiScale.json', () => ({ default: flipped }))
    const F = await import('./rqiScale')
    const FR = await import('./rqi')
    expect(F.RQI_LEVELS.map(l => l.value)).toEqual([5, 4, 3, 2, 1])
    expect(F.RQI_MODEL_LEVELS).toEqual([5, 4, 3, 2])
    for (const x of [0.7, 1, 1.5, 1.51, 2, 2.01, 2.5, 3, 3.5, 4, 4.5, 5, 6.2]) {
      const y = 6 - x
      expect(F.isBadRqi(y)).toBe(isBadRqi(x))
      expect(F.nearestRqiLevel(y)).toBe(6 - nearestRqiLevel(x))
      expect(F.towardWorseRqiLevel(y)).toBe(6 - towardWorseRqiLevel(x))
      expect(F.rqiScoreLabelHu(y)).toBe(rqiScoreLabelHu(x))
      expect(FR.getRQIColor(y)).toBe(getRQIColor(x))
      expect(FR.getRQILabel(y)).toBe(getRQILabel(x))
    }
    vi.doUnmock('./rqiScale.json')
  })
})
