import { describe, expect, it } from 'vitest'
import reducer, { actions, initialState } from './slice'
import type { LabelingState, LabelQueuePage, QueueItem } from './types'

const item = (id: number, extra: Partial<QueueItem> = {}): QueueItem => ({
  id,
  imageUrl: `images/sv_${id}_x.jpg`,
  latitude: 47.5,
  longitude: 19.05,
  streetViewUrl: 'https://example.invalid',
  reason: 'diverse',
  area: 'budapest',
  cellLabels: 0,
  modelRqi: 2,
  modelScore: 2.1,
  ...extra,
})

const stats = { totalLabelled: 100, labelledToday: 5, eligible: 1000, scored: 900 }

const withQueue = (ids: number[], extra: Partial<LabelingState> = {}): LabelingState => ({
  ...initialState,
  queue: ids.map(id => item(id)),
  stats: { ...stats },
  ...extra,
})

const page = (ids: number[], strategy: LabelQueuePage['strategy'] = 'MIXED'): LabelQueuePage => ({
  strategy,
  items: ids.map(id => item(id)),
  stats: { ...stats, totalLabelled: 200 },
})

describe('rating', () => {
  it('advances the queue, records history, queues a save and counts optimistically', () => {
    const s = reducer(withQueue([1, 2]), actions.rate({ id: 1, rqi: 3, elapsedMs: 1200 }))
    expect(s.queue.map(i => i.id)).toEqual([2])
    expect(s.history).toHaveLength(1)
    expect(s.history[0]).toMatchObject({ kind: 'rated', rqi: 3, status: 'saving' })
    expect(s.outbox).toEqual([
      expect.objectContaining({ kind: 'save', id: 1, rqi: 3, reason: 'diverse', revealed: false, elapsedMs: 1200 }),
    ])
    expect(s.sessionRated).toBe(1)
    expect(s.stats).toMatchObject({ totalLabelled: 101, labelledToday: 6 })
    expect(s.lastResult?.item.id).toBe(1)
  })

  it('ignores a double tap (stale id) so the next frame is not rated by accident', () => {
    let s = reducer(withQueue([1, 2]), actions.rate({ id: 1, rqi: 3 }))
    s = reducer(s, actions.rate({ id: 1, rqi: 4 }))
    expect(s.queue.map(i => i.id)).toEqual([2])
    expect(s.outbox).toHaveLength(1)
  })

  it('remembers whether the model was visible before rating', () => {
    let s = reducer(withQueue([1]), actions.toggleReveal())
    s = reducer(s, actions.rate({ id: 1, rqi: 2 }))
    expect(s.outbox[0]).toMatchObject({ revealed: true })
  })
})

describe('skip and undo', () => {
  it('skips without a server write and remembers the id', () => {
    const s = reducer(withQueue([1, 2]), actions.skip({ id: 1 }))
    expect(s.queue.map(i => i.id)).toEqual([2])
    expect(s.skipped).toEqual([1])
    expect(s.outbox).toEqual([])
  })

  it('undo of a skip brings the frame back and forgets the skip', () => {
    let s = reducer(withQueue([1, 2]), actions.skip({ id: 1 }))
    s = reducer(s, actions.undoLast())
    expect(s.queue.map(i => i.id)).toEqual([1, 2])
    expect(s.skipped).toEqual([])
    expect(s.outbox).toEqual([])
  })

  it('undo of a rating brings the frame back and queues a server revert after the save', () => {
    let s = reducer(withQueue([1, 2]), actions.rate({ id: 1, rqi: 3 }))
    s = reducer(s, actions.undoLast())
    expect(s.queue.map(i => i.id)).toEqual([1, 2])
    expect(s.outbox.map(w => w.kind)).toEqual(['save', 'undo'])
    expect(s.sessionRated).toBe(0)
    expect(s.stats).toMatchObject({ totalLabelled: 100, labelledToday: 5 })
  })

  it('undo on an empty history is a no-op', () => {
    const s0 = withQueue([1])
    expect(reducer(s0, actions.undoLast())).toEqual(s0)
  })
})

describe('server acknowledgements', () => {
  it('marks a save done and drops it from the outbox', () => {
    let s = reducer(withQueue([1, 2]), actions.rate({ id: 1, rqi: 3 }))
    const seq = s.outbox[0].seq
    s = reducer(s, actions.writeDone({ seq }))
    expect(s.outbox).toEqual([])
    expect(s.history[0]).toMatchObject({ status: 'saved' })
  })

  it('a failed save puts the frame back on screen and reverts the counters', () => {
    let s = reducer(withQueue([1, 2]), actions.rate({ id: 1, rqi: 3 }))
    s = reducer(s, actions.writeFailed({ seq: s.outbox[0].seq, message: 'boom' }))
    expect(s.queue.map(i => i.id)).toEqual([1, 2])
    expect(s.history).toEqual([])
    expect(s.sessionRated).toBe(0)
    expect(s.stats?.totalLabelled).toBe(100)
    expect(s.error).toContain('boom')
  })

  it('a failed undo keeps the screen as is and explains the label stayed', () => {
    let s = reducer(withQueue([1, 2]), actions.rate({ id: 1, rqi: 3 }))
    s = reducer(s, actions.undoLast())
    const undoSeq = s.outbox[1].seq
    s = reducer(s, actions.writeFailed({ seq: undoSeq, message: 'down' }))
    expect(s.queue.map(i => i.id)).toEqual([1, 2])
    expect(s.error).toContain('megmaradt')
  })
})

describe('queue pages', () => {
  it('appends new frames, skipping held ones, and takes server stats when idle', () => {
    let s = withQueue([1], { skipped: [7] })
    s = reducer(s, { type: 'labeling/fetchQueue/fulfilled', payload: page([1, 7, 8, 9]) })
    expect(s.queue.map(i => i.id)).toEqual([1, 8, 9])
    expect(s.exhausted).toBe(false)
    expect(s.stats?.totalLabelled).toBe(200)
  })

  it('keeps optimistic stats while writes are in flight', () => {
    let s = reducer(withQueue([1, 2]), actions.rate({ id: 1, rqi: 3 }))
    s = reducer(s, { type: 'labeling/fetchQueue/fulfilled', payload: page([5]) })
    expect(s.stats?.totalLabelled).toBe(101)
  })

  it('marks the strategy exhausted when a page brings nothing new', () => {
    const s = reducer(withQueue([1]), { type: 'labeling/fetchQueue/fulfilled', payload: page([1]) })
    expect(s.exhausted).toBe(true)
  })

  it('drops a page of the previous strategy after a switch', () => {
    let s = reducer(withQueue([1, 2, 3]), actions.setStrategy('UNCERTAIN'))
    expect(s.queue.map(i => i.id)).toEqual([1])
    s = reducer(s, { type: 'labeling/fetchQueue/fulfilled', payload: page([8, 9], 'MIXED') })
    expect(s.queue.map(i => i.id)).toEqual([1])
  })
})
