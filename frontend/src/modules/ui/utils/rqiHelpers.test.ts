import { describe, it, expect } from 'vitest'
import { getRQIColor, getRQILabel, resolveRqi } from './rqi'
import {
  RQI_AT_OR_BETTER_SIGN,
  RQI_AT_OR_WORSE_SIGN,
  RQI_BAD_FROM,
  RQI_LEVELS,
  RQI_UNKNOWN,
  RQI_WORSE_THAN_SIGN,
  atOrBetter,
  atOrWorse,
  betterThan,
  flipRqi,
  fromSeverity,
  nearestRqiLevel,
  rqiLevel,
  rqiScoreLabelHu,
  rqiTextColor,
  rqiValue,
  toSeverity,
  towardWorseRqiLevel,
  worseThan,
} from './rqiScale'
import type { RqiLevelKey } from './rqiScale'

// Expectations are written against level keys (never level numbers), so they
// hold for either numbering of the canonical scale.
const best = rqiValue('excellent')
const worst = rqiValue('very_poor')

describe('level lookup', () => {
  it('maps every key to its level and back', () => {
    for (const level of RQI_LEVELS) {
      expect(rqiValue(level.key)).toBe(level.value)
      expect(rqiLevel(level.value)).toBe(level)
    }
  })

  it('rejects an unknown key and has no level between or outside the values', () => {
    expect(() => rqiValue('superb' as RqiLevelKey)).toThrow('unknown RQI level key superb')
    expect(rqiLevel(2.5)).toBeUndefined()
    expect(rqiLevel(0)).toBeUndefined()
    expect(rqiLevel(6)).toBeUndefined()
  })
})

describe('ordering follows quality, not the numbers', () => {
  it('compares two levels by quality', () => {
    expect(betterThan(best, worst)).toBe(true)
    expect(betterThan(worst, best)).toBe(false)
    expect(betterThan(best, best)).toBe(false)
    expect(worseThan(worst, best)).toBe(true)
    expect(worseThan(best, worst)).toBe(false)
    expect(worseThan(worst, worst)).toBe(false)
  })

  it('the inclusive comparisons include the reference level', () => {
    const fair = rqiValue('fair')
    expect(atOrBetter(fair, fair)).toBe(true)
    expect(atOrWorse(fair, fair)).toBe(true)
    expect(atOrBetter(best, fair)).toBe(true)
    expect(atOrBetter(worst, fair)).toBe(false)
    expect(atOrWorse(worst, fair)).toBe(true)
    expect(atOrWorse(best, fair)).toBe(false)
  })

  it('the display signs agree with the comparisons', () => {
    const holds = (sign: string, x: number, ref: number) =>
      ({ '≤': x <= ref, '≥': x >= ref, '<': x < ref, '>': x > ref })[sign]
    const good = rqiValue('good')
    for (const level of RQI_LEVELS) {
      expect(holds(RQI_AT_OR_BETTER_SIGN, level.value, good)).toBe(atOrBetter(level.value, good))
      expect(holds(RQI_AT_OR_WORSE_SIGN, level.value, RQI_BAD_FROM)).toBe(atOrWorse(level.value, RQI_BAD_FROM))
      expect(holds(RQI_WORSE_THAN_SIGN, level.value, good)).toBe(worseThan(level.value, good))
    }
  })
})

describe('orientation helpers', () => {
  it('flipRqi mirrors the scale and is its own inverse', () => {
    expect(flipRqi(best)).toBe(worst)
    expect(flipRqi(worst)).toBe(best)
    expect(flipRqi(rqiValue('fair'))).toBe(rqiValue('fair'))
    expect(flipRqi(flipRqi(2.3))).toBeCloseTo(2.3, 10)
  })

  it('severity 1 is the best level and the conversion round-trips', () => {
    expect(fromSeverity(1)).toBe(best)
    expect(toSeverity(best)).toBe(1)
    expect(toSeverity(worst)).toBe(RQI_LEVELS.length)
    expect(toSeverity(fromSeverity(3.7))).toBeCloseTo(3.7, 10)
  })
})

describe('continuous score → level', () => {
  it('clamps scores beyond either end of the scale', () => {
    expect(nearestRqiLevel(fromSeverity(-3))).toBe(best)
    expect(nearestRqiLevel(fromSeverity(42))).toBe(worst)
    expect(towardWorseRqiLevel(fromSeverity(0.2))).toBe(best)
    expect(towardWorseRqiLevel(fromSeverity(9))).toBe(worst)
  })

  it('an exact half goes to the better level unless asked otherwise', () => {
    const half = fromSeverity(2.5)
    expect(nearestRqiLevel(half)).toBe(rqiValue('good'))
    expect(nearestRqiLevel(half, 'worse')).toBe(rqiValue('fair'))
  })
})

describe('Hungarian score label', () => {
  it('names the nearest level', () => {
    expect(rqiScoreLabelHu(fromSeverity(1))).toBe('Kiváló')
    expect(rqiScoreLabelHu(fromSeverity(2.2))).toBe('Jó')
    expect(rqiScoreLabelHu(fromSeverity(3))).toBe('Közepes')
    expect(rqiScoreLabelHu(fromSeverity(3.9))).toBe('Rossz')
    expect(rqiScoreLabelHu(fromSeverity(5))).toBe('Nagyon rossz')
  })

  it('says "Nincs adat" for a missing or non-finite score', () => {
    expect(RQI_UNKNOWN.label_hu).toBe('Nincs adat')
    for (const missing of [undefined, null, NaN, Infinity, -Infinity]) {
      expect(rqiScoreLabelHu(missing)).toBe('Nincs adat')
    }
  })
})

describe('rqiTextColor', () => {
  it('picks dark text on light fills and white on dark ones', () => {
    expect(rqiTextColor('#ffffff')).toBe('#111')
    expect(rqiTextColor('#facc15')).toBe('#111')
    expect(rqiTextColor('#000000')).toBe('#fff')
    expect(rqiTextColor('#1e3a8a')).toBe('#fff')
  })

  it('accepts short hex and a missing #', () => {
    expect(rqiTextColor('#fff')).toBe('#111')
    expect(rqiTextColor('000')).toBe('#fff')
    expect(rqiTextColor('ffffff')).toBe('#111')
  })
})

describe('rqi display helpers — missing scores', () => {
  it('colour and label of a null score are the "unknown" ones', () => {
    expect(getRQIColor(null)).toBe(RQI_UNKNOWN.color)
    expect(getRQILabel(null)).toBe(RQI_UNKNOWN.label_en)
  })

  it('a null DINO score counts as missing', () => {
    expect(resolveRqi({ rqi_score: 2, dino_rqi_score: null }, 'both')).toEqual({ score: 2, model: 'yolo', label: 'YOLO' })
    expect(resolveRqi({ rqi_score: 2, dino_rqi_score: null }, 'dino')).toEqual({
      score: 2,
      model: 'yolo',
      label: 'YOLO (Fallback)',
    })
  })

  it('resolves to no score (never null) when the point has none', () => {
    expect(resolveRqi({}, 'yolo')).toEqual({ score: undefined, model: 'yolo', label: 'YOLO' })
    expect(resolveRqi({ rqi_score: null }, 'both')).toEqual({ score: undefined, model: 'yolo', label: 'YOLO' })
    expect(resolveRqi({ rqi_score: null, dino_rqi_score: null }, 'dino')).toEqual({
      score: undefined,
      model: 'yolo',
      label: 'YOLO (Fallback)',
    })
  })

  it('yolo source ignores an available DINO score; a DINO score of 0 still counts', () => {
    expect(resolveRqi({ dino_rqi_score: 4 }, 'yolo')).toEqual({ score: undefined, model: 'yolo', label: 'YOLO' })
    expect(resolveRqi({ rqi_score: 2, dino_rqi_score: 0 }, 'both')).toEqual({ score: 0, model: 'dino', label: 'DINO' })
  })
})
