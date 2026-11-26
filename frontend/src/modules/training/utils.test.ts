import { describe, it, expect } from 'vitest'
import { calculateIoU, filterAnnotationsNMS, getBounds } from './utils'

type Pts = [number, number][]

const square = (x: number, y: number, size: number): Pts => [
  [x, y],
  [x + size, y],
  [x + size, y + size],
  [x, y + size],
]

describe('getBounds', () => {
  it('returns the bounding box of a polygon', () => {
    expect(
      getBounds([
        [10, 40],
        [30, 20],
        [25, 60],
      ]),
    ).toEqual({ x: 10, y: 20, w: 20, h: 40 })
  })

  it('returns an empty box for missing, non-array or empty input', () => {
    const empty = { x: 0, y: 0, w: 0, h: 0 }
    expect(getBounds([])).toEqual(empty)
    expect(getBounds(undefined as unknown as Pts)).toEqual(empty)
    expect(getBounds('nope' as unknown as Pts)).toEqual(empty)
  })

  it('accepts {x, y} points as well as [x, y] tuples', () => {
    const mixed = [{ x: 5, y: 7 }, [15, 27]] as unknown as Pts
    expect(getBounds(mixed)).toEqual({ x: 5, y: 7, w: 10, h: 20 })
  })

  it('skips points whose coordinates are not numbers', () => {
    const dirty = [
      ['a', 1],
      [2, 3],
      [6, 9],
    ] as unknown as Pts
    expect(getBounds(dirty)).toEqual({ x: 2, y: 3, w: 4, h: 6 })
  })

  it('returns an empty box when no point is usable', () => {
    const junk = [[null, null]] as unknown as Pts
    expect(getBounds(junk)).toEqual({ x: 0, y: 0, w: 0, h: 0 })
  })
})

describe('calculateIoU', () => {
  it('is 1 for identical boxes and 0 for disjoint ones', () => {
    const a = { id: 'a', points: square(0, 0, 10) }
    expect(calculateIoU(a, { id: 'b', points: square(0, 0, 10) })).toBe(1)
    expect(calculateIoU(a, { id: 'c', points: square(50, 50, 10) })).toBe(0)
  })

  it('is intersection over union for a partial overlap', () => {
    // 10x10 boxes shifted by 5 on x: intersection 50, union 150.
    const iou = calculateIoU({ id: 'a', points: square(0, 0, 10) }, { id: 'b', points: square(5, 0, 10) })
    expect(iou).toBeCloseTo(1 / 3, 10)
  })

  it('is 0 for boxes that only touch on an edge', () => {
    expect(calculateIoU({ id: 'a', points: square(0, 0, 10) }, { id: 'b', points: square(10, 0, 10) })).toBe(0)
  })

  it('is 0 when either annotation has no polygon', () => {
    expect(calculateIoU({ id: 'a' }, { id: 'b', points: square(0, 0, 10) })).toBe(0)
    expect(calculateIoU({ id: 'a', points: square(0, 0, 10) }, { id: 'b' })).toBe(0)
  })

  it('is 0 (not NaN) for two degenerate, zero-area boxes', () => {
    const dot: Pts = [[3, 3]]
    expect(calculateIoU({ id: 'a', points: dot }, { id: 'b', points: dot })).toBe(0)
  })
})

describe('filterAnnotationsNMS', () => {
  const strong = { id: 'strong', points: square(0, 0, 10), score: 0.9 }
  const weakOverlap = { id: 'weak', points: square(1, 0, 10), score: 0.4 }
  const elsewhere = { id: 'far', points: square(100, 100, 10), score: 0.2 }

  it('drops the lower-scored of two heavily overlapping annotations', () => {
    const kept = filterAnnotationsNMS([weakOverlap, elsewhere, strong])
    expect(kept.map(a => a.id)).toEqual(['strong', 'far'])
  })

  it('keeps both when the overlap does not exceed the threshold', () => {
    // IoU of `strong` and `weakOverlap` is 90 / 110 ≈ 0.818.
    expect(filterAnnotationsNMS([strong, weakOverlap], 0.9).map(a => a.id)).toEqual(['strong', 'weak'])
    expect(filterAnnotationsNMS([strong, weakOverlap], 0.8).map(a => a.id)).toEqual(['strong'])
  })

  it('treats a missing score as 0, so scored detections win', () => {
    const manual = { id: 'manual', points: square(0, 0, 10) }
    expect(filterAnnotationsNMS([manual, strong]).map(a => a.id)).toEqual(['strong'])
  })

  it('does not mutate the input and handles an empty list', () => {
    const input = [weakOverlap, strong]
    filterAnnotationsNMS(input)
    expect(input.map(a => a.id)).toEqual(['weak', 'strong'])
    expect(filterAnnotationsNMS([])).toEqual([])
  })
})
