import { describe, it, expect } from 'vitest'
import { getRQIColor, getRQILabel, resolveRqi } from './rqi'
import { RQI_UNKNOWN, fromSeverity as sv, rqiLevel, rqiValue } from './rqiScale'
import type { RqiLevelKey } from './rqiScale'

// Scores written as sv(severity) (1 = best) so the expectations hold for
// either numbering of the canonical scale.

describe('getRQIColor', () => {
  it('returns gray for unknown scores', () => {
    expect(getRQIColor(undefined)).toBe(RQI_UNKNOWN.color)
    expect(getRQIColor(null)).toBe(RQI_UNKNOWN.color)
  })

  it('maps score ranges to colours', () => {
    const c = (key: RqiLevelKey) => rqiLevel(rqiValue(key))!.color
    expect(getRQIColor(sv(1))).toBe(c('excellent'))
    expect(getRQIColor(sv(1.5))).toBe(c('good')) // rounds toward the worse level
    expect(getRQIColor(sv(2))).toBe(c('good'))
    expect(getRQIColor(sv(2.5))).toBe(c('fair'))
    expect(getRQIColor(sv(3))).toBe(c('fair'))
    expect(getRQIColor(sv(3.5))).toBe(c('poor'))
    expect(getRQIColor(sv(4))).toBe(c('poor'))
    expect(getRQIColor(sv(4.5))).toBe(c('very_poor'))
  })
})

describe('getRQILabel', () => {
  it('labels each quality band', () => {
    expect(getRQILabel(sv(1))).toBe('Excellent')
    expect(getRQILabel(sv(2))).toBe('Good')
    expect(getRQILabel(sv(3))).toBe('Fair')
    expect(getRQILabel(sv(4))).toBe('Poor')
    expect(getRQILabel(sv(5))).toBe('Critical')
    expect(getRQILabel(undefined)).toBe('Unknown')
  })
})

describe('resolveRqi', () => {
  const point = { rqi_score: 2, dino_rqi_score: 4 }

  it('yolo source uses the YOLO score', () => {
    expect(resolveRqi(point, 'yolo')).toEqual({ score: 2, model: 'yolo', label: 'YOLO' })
  })

  it('dino source uses the DINO score', () => {
    expect(resolveRqi(point, 'dino')).toEqual({ score: 4, model: 'dino', label: 'DINO' })
  })

  it('both prefers DINO when available', () => {
    expect(resolveRqi(point, 'both')).toEqual({ score: 4, model: 'dino', label: 'DINO' })
  })

  it('dino falls back to YOLO when the DINO score is missing', () => {
    expect(resolveRqi({ rqi_score: 3 }, 'dino')).toEqual({
      score: 3,
      model: 'yolo',
      label: 'YOLO (Fallback)',
    })
  })

  it('both falls back to YOLO when the DINO score is missing', () => {
    expect(resolveRqi({ rqi_score: 3 }, 'both')).toEqual({ score: 3, model: 'yolo', label: 'YOLO' })
  })
})
