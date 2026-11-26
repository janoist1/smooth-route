import { describe, it, expect, afterEach, vi } from 'vitest'
import {
  RETRAIN_EVERY,
  loadRetrainAck,
  loadSkipped,
  loadStrategy,
  newClientId,
  retrainMilestone,
  saveRetrainAck,
  saveSkipped,
  saveStrategy,
} from './logic'

afterEach(() => {
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
  window.localStorage.clear()
})

describe('retrain hint acknowledgement (sprint)', () => {
  it('starts at 0 and remembers the acknowledged milestone', () => {
    expect(loadRetrainAck()).toBe(0)
    saveRetrainAck(RETRAIN_EVERY)
    expect(loadRetrainAck()).toBe(RETRAIN_EVERY)
  })

  it('an acknowledged milestone is not announced again, the next one is', () => {
    saveRetrainAck(RETRAIN_EVERY)
    expect(retrainMilestone(RETRAIN_EVERY + 10, loadRetrainAck())).toBeNull()
    expect(retrainMilestone(2 * RETRAIN_EVERY, loadRetrainAck())).toBe(2 * RETRAIN_EVERY)
  })

  it('treats a corrupted stored value as "nothing acknowledged"', () => {
    window.localStorage.setItem('quickLabel.retrainAck', 'abc')
    expect(loadRetrainAck()).toBe(0)
  })
})

describe('per-browser memory without storage (private mode, blocked site data)', () => {
  const blockStorage = () => {
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new Error('SecurityError')
    })
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('QuotaExceededError')
    })
  }

  it('reads fall back to the defaults', () => {
    blockStorage()
    expect(loadRetrainAck()).toBe(0)
    expect(loadSkipped()).toEqual([])
    expect(loadStrategy()).toBe('MIXED')
  })

  it('writes are silently dropped', () => {
    blockStorage()
    expect(() => saveRetrainAck(RETRAIN_EVERY)).not.toThrow()
    expect(() => saveSkipped([1, 2, 3])).not.toThrow()
    expect(() => saveStrategy('UNCERTAIN')).not.toThrow()
  })

  it('ignores stored skips that are not a list of integer ids', () => {
    window.localStorage.setItem('quickLabel.skipped', JSON.stringify({ 1: true }))
    expect(loadSkipped()).toEqual([])
    window.localStorage.setItem('quickLabel.skipped', JSON.stringify([1, 'x', 2.5, null, 7]))
    expect(loadSkipped()).toEqual([1, 7])
  })
})

describe('newClientId', () => {
  it('gives every label its own id', () => {
    const ids = new Set(Array.from({ length: 50 }, () => newClientId()))
    expect(ids.size).toBe(50)
  })

  it('still produces a usable id where crypto.randomUUID is missing', () => {
    vi.stubGlobal('crypto', {})
    const a = newClientId()
    const b = newClientId()
    expect(a).toMatch(/^[0-9a-z]+-[0-9a-z]+$/)
    expect(a).not.toBe(b)
  })
})
