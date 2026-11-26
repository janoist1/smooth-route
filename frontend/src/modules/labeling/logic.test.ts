import { afterEach, describe, expect, it } from 'vitest'
import { RQI_LEVELS } from '../ui'
import {
  agreement,
  canUndo,
  excludeIds,
  imageSrc,
  isOldCapture,
  keyToAction,
  levelOf,
  loadSkipped,
  loadStrategy,
  mergeQueue,
  needsRefill,
  prefetchUrls,
  pushHistory,
  RATING_KEY_RANGE,
  RATING_LEVELS,
  reasonLabel,
  REFILL_AT,
  saveSkipped,
  saveStrategy,
  SKIP_MEMORY,
} from './logic'
import type { HistoryEntry, QueueItem } from './types'

export const item = (id: number, extra: Partial<QueueItem> = {}): QueueItem => ({
  id,
  imageUrl: `images/sv_${id}_x.jpg`,
  latitude: 47.5,
  longitude: 19.05,
  streetViewUrl: 'https://example.invalid',
  reason: 'diverse',
  area: 'budapest',
  cellLabels: 0,
  ...extra,
})

describe('rating levels come from the shared scale', () => {
  it('uses every level of the canonical scale, best to worst', () => {
    expect(RATING_LEVELS).toBe(RQI_LEVELS)
    expect(RATING_LEVELS.map(l => l.label_hu)).toEqual(['Kiváló', 'Jó', 'Közepes', 'Rossz', 'Nagyon rossz'])
  })

  it('looks levels up by stored value', () => {
    for (const level of RATING_LEVELS) expect(levelOf(level.value)).toBe(level)
    expect(levelOf(null)).toBeUndefined()
    expect(levelOf(99)).toBeUndefined()
  })
})

describe('keyToAction', () => {
  it('maps the digit of every scale level to a rating, other digits to nothing', () => {
    for (const level of RATING_LEVELS) {
      expect(keyToAction(String(level.value))).toEqual({ type: 'rate', rqi: level.value })
    }
    const values = RATING_LEVELS.map(l => l.value)
    expect(keyToAction(String(Math.max(...values) + 1))).toBeNull()
    expect(keyToAction('0')).toBeNull()
    expect(RATING_KEY_RANGE).toBe(`${Math.min(...values)}–${Math.max(...values)}`)
  })

  it('maps arrows and letters to skip / undo / reveal / zoom', () => {
    expect(keyToAction('ArrowRight')).toEqual({ type: 'skip' })
    expect(keyToAction('s')).toEqual({ type: 'skip' })
    expect(keyToAction('ArrowLeft')).toEqual({ type: 'undo' })
    expect(keyToAction('Backspace')).toEqual({ type: 'undo' })
    expect(keyToAction('z')).toEqual({ type: 'undo' })
    expect(keyToAction('m')).toEqual({ type: 'reveal' })
    expect(keyToAction(' ')).toEqual({ type: 'zoom' })
    expect(keyToAction('Enter')).toBeNull()
  })

  it('leaves browser shortcuts alone', () => {
    expect(keyToAction('1', { metaKey: true })).toBeNull()
    expect(keyToAction('ArrowLeft', { ctrlKey: true })).toBeNull()
    expect(keyToAction('z', { altKey: true })).toBeNull()
  })
})

describe('queue bookkeeping', () => {
  const rated: HistoryEntry = { kind: 'rated', seq: 1, item: item(2), rqi: 3, status: 'saved', revealed: false }
  const skipped: HistoryEntry = { kind: 'skipped', item: item(3) }

  it('excludes everything the client holds, without duplicates', () => {
    const ids = excludeIds([item(1), item(2)], [rated, skipped], [3, 9])
    expect(ids.sort()).toEqual([1, 2, 3, 9])
  })

  it('merges only new frames, keeping order', () => {
    const merged = mergeQueue([item(1)], [item(1), item(5), item(2), item(6), item(5)], [2])
    expect(merged.map(i => i.id)).toEqual([1, 5, 6])
  })

  it('returns the same array when nothing is new (lets the slice detect exhaustion)', () => {
    const q = [item(1)]
    expect(mergeQueue(q, [item(1)], [])).toBe(q)
  })

  it('refills below the threshold unless loading or exhausted', () => {
    expect(needsRefill(REFILL_AT - 1, false, false)).toBe(true)
    expect(needsRefill(REFILL_AT, false, false)).toBe(false)
    expect(needsRefill(0, true, false)).toBe(false)
    expect(needsRefill(0, false, true)).toBe(false)
  })

  it('prefetches the frames after the current one', () => {
    const q = [item(1), item(2), item(3), item(4)]
    expect(prefetchUrls(q, 2)).toEqual(['/images/sv_2_x.jpg', '/images/sv_3_x.jpg'])
    expect(prefetchUrls([item(1)])).toEqual([])
  })

  it('caps the undo history', () => {
    let h: HistoryEntry[] = []
    for (let i = 0; i < 5; i++) h = pushHistory(h, { kind: 'skipped', item: item(i) }, 3)
    expect(h.map(e => e.item.id)).toEqual([2, 3, 4])
    expect(canUndo(h)).toBe(true)
    expect(canUndo([])).toBe(false)
  })
})

describe('labels', () => {
  it('explains why a frame was picked', () => {
    expect(reasonLabel(item(1))).toBe('Új cella · Budapest')
    expect(reasonLabel(item(1, { cellLabels: 2, area: 'other' }))).toBe('Ritka cella · Új terület')
    expect(reasonLabel(item(1, { reason: 'uncertain', boundary: '2|3' }))).toBe('Bizonytalan · 2|3 határ')
  })

  it('compares the human rating with the model only after the fact', () => {
    expect(agreement(2, 2)).toBe('same')
    expect(agreement(2, 3)).toBe('near')
    expect(agreement(1, 4)).toBe('far')
    expect(agreement(1, null)).toBeNull()
  })

  it('flags captures older than four years', () => {
    const now = new Date(2026, 10, 26)
    expect(isOldCapture('2021-06', now)).toBe(true)
    expect(isOldCapture('2023-01', now)).toBe(false)
    expect(isOldCapture(null, now)).toBe(false)
    expect(isOldCapture('garbage', now)).toBe(false)
  })

  it('builds same-origin image paths', () => {
    expect(imageSrc('images/a.jpg')).toBe('/images/a.jpg')
    expect(imageSrc('/images/a.jpg')).toBe('/images/a.jpg')
  })
})

describe('per-browser memory', () => {
  afterEach(() => window.localStorage.clear())

  it('round-trips skipped ids and caps them', () => {
    saveSkipped(Array.from({ length: SKIP_MEMORY + 10 }, (_, i) => i))
    const back = loadSkipped()
    expect(back).toHaveLength(SKIP_MEMORY)
    expect(back[0]).toBe(10)
  })

  it('survives garbage and defaults the strategy', () => {
    window.localStorage.setItem('quickLabel.skipped', '{not json')
    window.localStorage.setItem('quickLabel.strategy', 'RANDOM')
    expect(loadSkipped()).toEqual([])
    expect(loadStrategy()).toBe('MIXED')
    saveStrategy('UNCERTAIN')
    expect(loadStrategy()).toBe('UNCERTAIN')
  })
})
