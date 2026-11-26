import { describe, expect, it, vi } from 'vitest'
import scaleJson from './rqiScale.json'
import localRaw from './rqiScale.json?raw'
import sharedRaw from '../../../../../shared/rqi_scale.json?raw'
import {
  RQI_BAD_FROM,
  RQI_LEVELS,
  RQI_MODEL_LEVELS,
  RQI_SCALE,
  RQI_UNKNOWN,
  compareWorstFirst,
  fromSeverity as sv,
  isBadRqi,
  nearestRqiLevel,
  rqiLevel,
  rqiScoreLabelHu,
  rqiTextColor,
  rqiValue,
  toSeverity,
  towardWorseRqiLevel,
} from './rqiScale'
import { getRQIColor, getRQILabel } from './rqi'

// Expectations use sv(severity) (1 = best) so they hold for either numbering.
// After a flip (scripts/sync_rqi_scale.py --flip) only the direction pin fails.

describe('canonical RQI scale definition', () => {
  it('frontend copy is byte-identical to shared/rqi_scale.json', () => {
    // On drift run: python scripts/sync_rqi_scale.py
    expect(localRaw).toBe(sharedRaw)
  })

  it('has five levels with the Hungarian UI labels, best first', () => {
    expect(RQI_LEVELS.map(l => l.label_hu)).toEqual(['Kiváló', 'Jó', 'Közepes', 'Rossz', 'Nagyon rossz'])
    expect(RQI_LEVELS.map(l => l.key)).toEqual(['excellent', 'good', 'fair', 'poor', 'very_poor'])
    expect(RQI_LEVELS.map(l => toSeverity(l.value))).toEqual([1, 2, 3, 4, 5])
  })

  it('direction pin: 5 = Kiváló since the owner flip (changes only on a deliberate flip)', () => {
    expect(RQI_SCALE.direction).toBe('higher_is_better')
    expect(RQI_LEVELS.map(l => l.value)).toEqual([5, 4, 3, 2, 1])
    expect(RQI_MODEL_LEVELS).toEqual([5, 4, 3, 2])
    expect(RQI_BAD_FROM).toBe(3)
  })

  it('every level has its own colour, distinct from "no data"', () => {
    const colours = RQI_LEVELS.map(l => l.color.toLowerCase())
    expect(new Set([...colours, RQI_UNKNOWN.color.toLowerCase()]).size).toBe(RQI_LEVELS.length + 1)
  })

  it('picks readable badge text on each level colour', () => {
    expect(rqiTextColor(rqiLevel(rqiValue('excellent'))!.color)).toBe('#fff') // dark blue
    expect(rqiTextColor(rqiLevel(rqiValue('fair'))!.color)).toBe('#111') // amber
    expect(rqiTextColor(rqiLevel(rqiValue('very_poor'))!.color)).toBe('#fff') // dark red
  })

  it('model contract: Nagyon rossz is never predicted; bad road from Közepes', () => {
    expect(RQI_MODEL_LEVELS.map(toSeverity)).toEqual([1, 2, 3, 4])
    expect(RQI_BAD_FROM).toBe(rqiValue('fair'))
    expect(rqiLevel(rqiValue('fair'))?.label_hu).toBe('Közepes')
    expect(rqiLevel(2.5)).toBeUndefined()
  })
})

describe('helpers', () => {
  it('bad road = at or worse than Közepes', () => {
    expect([1, 2, 2.9, 3, 4, 5].map(x => isBadRqi(sv(x)))).toEqual([false, false, false, true, true, true])
  })

  it('sorts worst first', () => {
    expect([1, 4, 2, 3].map(sv).sort(compareWorstFirst)).toEqual([4, 3, 2, 1].map(sv))
  })

  it('rounds continuous scores', () => {
    expect([0.2, 1.5, 1.51, 2.5, 3.5, 4.5, 4.6, 9].map(s => nearestRqiLevel(sv(s)))).toEqual(
      [1, 1, 2, 2, 3, 4, 5, 5].map(sv),
    )
    expect([1.49, 1.5, 2.5, 4.5].map(s => nearestRqiLevel(sv(s), 'worse'))).toEqual([1, 2, 3, 5].map(sv))
    expect([0, 2, 2.01, 3, 4, 4.01, 7].map(s => towardWorseRqiLevel(sv(s)))).toEqual(
      [1, 2, 3, 3, 4, 5, 5].map(sv),
    )
  })

  it('Hungarian score label', () => {
    expect(rqiScoreLabelHu(sv(1))).toBe('Kiváló')
    expect(rqiScoreLabelHu(sv(1.5))).toBe('Kiváló')
    expect(rqiScoreLabelHu(sv(2.6))).toBe('Közepes')
    expect(rqiScoreLabelHu(sv(4.8))).toBe('Nagyon rossz')
    expect(rqiScoreLabelHu(null)).toBe('Nincs adat')
  })
})

// The pre-centralisation rules, in severity (1 = best). Colour: the legacy
// whole-number bands (2.0 stays, 2.01 is the next level), plus the 1|2 cut now
// that Kiváló and Jó have different colours. Label: verbatim.
const legacyColorBand = (score: number): number => {
  if (score <= 1.0) return 1
  if (score <= 2.0) return 2
  if (score <= 3.0) return 3
  if (score <= 4.0) return 4
  return 5
}
const legacyLabel = (score: number): string => {
  if (score <= 1.5) return 'Excellent'
  if (score <= 2.5) return 'Good'
  if (score <= 3.5) return 'Fair'
  if (score <= 4.5) return 'Poor'
  return 'Critical'
}

// The legacy rules were written for 1 = best, i.e. in severity terms.
describe('getRQIColor / getRQILabel are unchanged', () => {
  const samples: number[] = []
  for (let s = -1; s <= 7.0001; s += 0.01) samples.push(Math.round(s * 100) / 100)

  it('colour follows the legacy bands on a 0.01 grid', () => {
    for (const s of samples) {
      expect(getRQIColor(sv(s)), `severity ${s}`).toBe(rqiLevel(sv(legacyColorBand(s)))!.color)
    }
  })

  it('label matches the legacy bands on a 0.01 grid', () => {
    for (const s of samples) expect(getRQILabel(sv(s)), `severity ${s}`).toBe(legacyLabel(s))
  })
})

describe('the mirrored scale answers the same on mirrored data', () => {
  it('mirrors levels and keeps labels, colours and the bad-road decision', async () => {
    const flipped = {
      ...scaleJson,
      direction: scaleJson.direction === 'lower_is_better' ? 'higher_is_better' : 'lower_is_better',
      bad_from: 6 - scaleJson.bad_from,
      model_levels: scaleJson.model_levels.map(v => 6 - v).sort(),
      levels: scaleJson.levels.map(l => ({ ...l, value: 6 - l.value })),
    }
    vi.resetModules()
    vi.doMock('./rqiScale.json', () => ({ default: flipped }))
    const F = await import('./rqiScale')
    const FR = await import('./rqi')
    expect(F.RQI_LEVELS.map(l => l.value)).toEqual(RQI_LEVELS.map(l => 6 - l.value))
    expect(F.RQI_MODEL_LEVELS).toEqual(RQI_MODEL_LEVELS.map(v => 6 - v))
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
