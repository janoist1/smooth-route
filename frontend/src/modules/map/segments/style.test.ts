import { describe, it, expect } from 'vitest'
import { RQI_UNKNOWN, fromSeverity as sv, rqiLevel, rqiValue } from '../../ui'
import type { RqiLevelKey } from '../../ui'
import {
  FRAME_DOT_MIN_ZOOM,
  SEGMENT_MIN_ZOOM,
  isStaleSegment,
  layersForZoom,
  segmentCasingStyle,
  segmentOpacity,
  segmentStyle,
  segmentWeight,
  selectionHaloStyle,
} from './style'

describe('layersForZoom', () => {
  it('pins the thresholds the backend contract relies on', () => {
    expect(SEGMENT_MIN_ZOOM).toBe(13) // roadSegments returns [] below 13
    expect(FRAME_DOT_MIN_ZOOM).toBe(16)
  })

  it('shows only the grid when zoomed out', () => {
    expect(layersForZoom(5)).toEqual({ grid: true, segments: false, frames: false })
    expect(layersForZoom(12)).toEqual({ grid: true, segments: false, frames: false })
  })

  it('shows segments without frame dots from zoom 13 to 15', () => {
    for (const zoom of [13, 14, 15]) {
      expect(layersForZoom(zoom)).toEqual({ grid: false, segments: true, frames: false })
    }
  })

  it('adds the frame dots at street level', () => {
    expect(layersForZoom(16)).toEqual({ grid: false, segments: true, frames: true })
    expect(layersForZoom(19)).toEqual({ grid: false, segments: true, frames: true })
  })

  it('falls back to the legacy grid/points split without the segment API', () => {
    expect(layersForZoom(13, false)).toEqual({ grid: true, segments: false, frames: false })
    expect(layersForZoom(14, false)).toEqual({ grid: false, segments: false, frames: true })
    expect(layersForZoom(17, false)).toEqual({ grid: false, segments: false, frames: true })
  })
})

describe('segmentWeight', () => {
  it('grows with the zoom and is clamped at both ends', () => {
    expect(segmentWeight(10)).toBe(3)
    expect(segmentWeight(13)).toBe(3)
    expect(segmentWeight(14)).toBe(4)
    expect(segmentWeight(15)).toBe(5)
    expect(segmentWeight(16)).toBe(6)
    expect(segmentWeight(17)).toBe(7)
    expect(segmentWeight(20)).toBe(7)
  })
})

describe('segmentOpacity', () => {
  it('maps confidence 0..1 to 0.35..1', () => {
    expect(segmentOpacity(0)).toBeCloseTo(0.35)
    expect(segmentOpacity(0.5)).toBeCloseTo(0.675)
    expect(segmentOpacity(1)).toBeCloseTo(1)
  })

  it('clamps out-of-range and treats a missing confidence as none', () => {
    expect(segmentOpacity(-1)).toBeCloseTo(0.35)
    expect(segmentOpacity(7)).toBeCloseTo(1)
    expect(segmentOpacity(null)).toBeCloseTo(0.35)
    expect(segmentOpacity(undefined)).toBeCloseTo(0.35)
    expect(segmentOpacity(NaN)).toBeCloseTo(0.35)
  })
})

// Classes given as severity (1 = best) via sv(): valid for either numbering.
const colorOf = (key: RqiLevelKey) => rqiLevel(rqiValue(key))!.color

describe('segmentStyle', () => {
  const seg = (severity: number | null, confidence: number, confidenceLevel: string) => ({
    rqi: severity === null ? null : sv(severity),
    confidence,
    confidenceLevel,
  })

  it('colours by quality class (same colours as the dots and the grid)', () => {
    expect(segmentStyle(seg(1, 1, 'high'), 14).color).toBe(colorOf('excellent'))
    expect(segmentStyle(seg(2, 1, 'high'), 14).color).toBe(colorOf('good'))
    expect(segmentStyle(seg(3, 1, 'high'), 14).color).toBe(colorOf('fair'))
    expect(segmentStyle(seg(4, 1, 'high'), 14).color).toBe(colorOf('poor'))
    expect(segmentStyle(seg(null, 1, 'high'), 14).color).toBe(RQI_UNKNOWN.color)
  })

  it('draws a confident segment solid and strong', () => {
    expect(segmentStyle(seg(2, 1, 'high'), 15)).toEqual({
      color: colorOf('good'),
      weight: 5,
      opacity: 1,
      lineCap: 'round',
    })
  })

  it('fades a less confident segment but keeps it solid', () => {
    const style = segmentStyle(seg(3, 0.5, 'medium'), 14)
    expect(style.opacity).toBeCloseTo(0.675)
    expect(style.dashArray).toBeUndefined()
  })

  it('dashes a low-confidence segment, scaled to the line weight', () => {
    const style = segmentStyle(seg(4, 0.2, 'low'), 14)
    expect(style.opacity).toBeCloseTo(0.48)
    expect(style.dashArray).toBe('8 6')
    expect(style.lineCap).toBe('butt')
    expect(segmentStyle(seg(4, 0.2, 'low'), 16).dashArray).toBe('12 9')
  })

  it('thickens and brightens on hover', () => {
    const base = segmentStyle(seg(3, 0.5, 'medium'), 14)
    const hovered = segmentStyle(seg(3, 0.5, 'medium'), 14, { hovered: true })
    expect(hovered.weight).toBe(base.weight + 2)
    expect(hovered.opacity).toBeGreaterThan(base.opacity)
    expect(segmentStyle(seg(3, 1, 'high'), 14, { hovered: true }).opacity).toBe(1)
  })

  it('dims a segment hidden by the old-image filter', () => {
    expect(segmentStyle(seg(2, 1, 'high'), 14, { dimmed: true }).opacity).toBeCloseTo(0.35)
  })
})

describe('segmentCasingStyle', () => {
  it('is a slightly wider dark line that follows the opacity and the dashes', () => {
    const solid = segmentStyle({ rqi: sv(2), confidence: 1, confidenceLevel: 'high' }, 14)
    expect(segmentCasingStyle(solid)).toEqual({
      color: '#0b1220',
      weight: 6,
      opacity: 0.6,
      lineCap: 'round',
    })

    const dashed = segmentStyle({ rqi: sv(4), confidence: 0.2, confidenceLevel: 'low' }, 14)
    const casing = segmentCasingStyle(dashed)
    expect(casing.dashArray).toBe(dashed.dashArray)
    expect(casing.lineCap).toBe('butt')
    expect(casing.opacity).toBeLessThan(dashed.opacity)
  })
})

describe('selection + staleness', () => {
  it('halo is wider than the segment it surrounds', () => {
    expect(selectionHaloStyle(14).weight).toBeGreaterThan(segmentWeight(14))
    expect(selectionHaloStyle(14).color).toBe('#ffffff')
  })

  it('a segment is stale only when even its newest image is old', () => {
    const now = new Date(2026, 10, 18)
    expect(isStaleSegment({ captureDateMax: '2019-06' }, now)).toBe(true)
    expect(isStaleSegment({ captureDateMax: '2025-06' }, now)).toBe(false)
    expect(isStaleSegment({ captureDateMax: null }, now)).toBe(false)
  })
})
