import { describe, it, expect } from 'vitest'
import { getRQIColor, getRQILabel, resolveRqi } from './rqi'

describe('getRQIColor', () => {
  it('returns gray for unknown scores', () => {
    expect(getRQIColor(undefined)).toBe('#888')
    expect(getRQIColor(null)).toBe('#888')
  })

  it('maps score ranges to colours', () => {
    expect(getRQIColor(1)).toBe('#4ade80') // green
    expect(getRQIColor(2)).toBe('#4ade80')
    expect(getRQIColor(2.5)).toBe('#facc15') // yellow
    expect(getRQIColor(3)).toBe('#facc15')
    expect(getRQIColor(3.5)).toBe('#f87171') // red
    expect(getRQIColor(4)).toBe('#f87171')
    expect(getRQIColor(4.5)).toBe('#ef4444') // dark red
  })
})

describe('getRQILabel', () => {
  it('labels each quality band', () => {
    expect(getRQILabel(1)).toBe('Excellent')
    expect(getRQILabel(2)).toBe('Good')
    expect(getRQILabel(3)).toBe('Fair')
    expect(getRQILabel(4)).toBe('Poor')
    expect(getRQILabel(5)).toBe('Critical')
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
