import { describe, expect, it } from 'vitest'
import reducer, { actions, initialState } from './slice'
import { pairExcludeIds, pairKeyToAction, retrainMilestone, RETRAIN_EVERY } from './logic'
import type { LabelingState, PairItem, QueueItem } from './types'

const item = (id: number): QueueItem => ({
  id,
  imageUrl: `images/sv_${id}.jpg`,
  latitude: 47.5,
  longitude: 19.05,
  streetViewUrl: 'https://example.invalid',
  reason: 'pair',
  area: 'budapest',
  cellLabels: 0,
})
const pair = (a: number, b: number): PairItem => ({ a: item(a), b: item(b), scoreGap: 0.1 })
const withPairs = (...pairs: PairItem[]): LabelingState => ({ ...initialState, mode: 'pair', pairs })

describe('sprint retrain hint', () => {
  it('fires once per RETRAIN_EVERY labels until acknowledged', () => {
    expect(retrainMilestone(RETRAIN_EVERY - 1, 0)).toBeNull()
    expect(retrainMilestone(RETRAIN_EVERY, 0)).toBe(RETRAIN_EVERY)
    expect(retrainMilestone(RETRAIN_EVERY + 50, RETRAIN_EVERY)).toBeNull()
    expect(retrainMilestone(2 * RETRAIN_EVERY + 1, RETRAIN_EVERY)).toBe(2 * RETRAIN_EVERY)
    expect(retrainMilestone(undefined, 0)).toBeNull()
  })

  it('acknowledging keeps the highest milestone', () => {
    let s = reducer(initialState, actions.ackRetrain(400))
    s = reducer(s, actions.ackRetrain(200))
    expect(s.retrainAck).toBe(400)
  })
})

describe('pairwise keys and exclusions', () => {
  it('maps ← ↓ → and undo', () => {
    expect(pairKeyToAction('ArrowLeft')).toEqual({ type: 'judge', result: 'A' })
    expect(pairKeyToAction('ArrowDown')).toEqual({ type: 'judge', result: 'EQUAL' })
    expect(pairKeyToAction('ArrowRight')).toEqual({ type: 'judge', result: 'B' })
    expect(pairKeyToAction('Backspace')).toEqual({ type: 'undo' })
    expect(pairKeyToAction('1')).toBeNull()
    expect(pairKeyToAction('ArrowLeft', { metaKey: true })).toBeNull()
  })

  it('excludes every frame held or judged here', () => {
    const ids = pairExcludeIds([pair(1, 2)], [{ pair: pair(3, 4) }])
    expect(ids.sort()).toEqual([1, 2, 3, 4])
  })
})

describe('pair reducer', () => {
  it.each(['before', 'during'])('keeps optimistic counts when a pair page starts %s saving and restores a failed pair', timing => {
    let s = withPairs(pair(1, 2), pair(3, 4))
    if (timing === 'before') s = reducer(s, { type: actions.fetchPairs.pending.type })
    s = reducer(s, actions.judgePair({ aId: 1, result: 'A', clientId: 'c1' }))
    if (timing === 'during') s = reducer(s, { type: actions.fetchPairs.pending.type })
    s = reducer(s, actions.writeDone({ seq: s.outbox[0].seq }))
    s = reducer(s, { type: actions.fetchPairs.fulfilled.type, payload: { pairs: [], judged: 0 } })
    expect(s.pairsJudged).toBe(1)
    s = reducer(s, actions.judgePair({ aId: 3, result: 'B', clientId: 'c2' }))
    s = reducer(s, actions.writeFailed({ seq: s.outbox[0].seq, message: 'offline' }))
    expect(s.pairs).toEqual([pair(3, 4)])
    expect(s.pairHistory.map(h => h.clientId)).toEqual(['c1'])
    expect(s.pairsJudged).toBe(1)
    expect(s.error).toContain('offline')
  })

  it('a failed pair save drops its undo without restoring or counting the pair twice', () => {
    let s = reducer(withPairs(pair(1, 2)), actions.judgePair({ aId: 1, result: 'A', clientId: 'c1' }))
    const seq = s.outbox[0].seq
    s = reducer(s, actions.undoPair())
    s = reducer(s, actions.writeFailed({ seq, message: 'offline' }))
    expect(s.pairs).toEqual([pair(1, 2)])
    expect(s.outbox).toEqual([])
    expect(s.pairsJudged).toBe(0)
  })
  it('judging advances, records history and queues an ordered write', () => {
    const s = reducer(withPairs(pair(1, 2), pair(3, 4)), actions.judgePair({ aId: 1, result: 'B', clientId: 'c1' }))
    expect(s.pairs.map(p => p.a.id)).toEqual([3])
    expect(s.outbox).toEqual([expect.objectContaining({ kind: 'pair', clientId: 'c1', aId: 1, bId: 2, result: 'B' })])
    expect(s.pairsJudged).toBe(1)
  })

  it('a double tap does not judge the next pair; undo brings the pair back', () => {
    let s = reducer(withPairs(pair(1, 2), pair(3, 4)), actions.judgePair({ aId: 1, result: 'A', clientId: 'c1' }))
    s = reducer(s, actions.judgePair({ aId: 1, result: 'A', clientId: 'c2' }))
    expect(s.outbox).toHaveLength(1)
    s = reducer(s, actions.undoPair())
    expect(s.pairs.map(p => p.a.id)).toEqual([1, 3])
    expect(s.outbox.map(w => w.kind)).toEqual(['pair', 'pairUndo'])
    expect(s.pairsJudged).toBe(0)
  })

  it('a page merges only frames not already on screen', () => {
    const pending = reducer(withPairs(pair(1, 2)), { type: actions.fetchPairs.pending.type })
    const s = reducer(pending, {
      type: 'labeling/fetchPairs/fulfilled',
      payload: { pairs: [pair(2, 9), pair(5, 6)], judged: 7 },
    })
    expect(s.pairs.map(p => p.a.id)).toEqual([1, 5])
    expect(s.pairsJudged).toBe(7)
  })
})
