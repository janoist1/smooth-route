// Integration test of the label writer: real store + reducer + sagas, with a
// slow fake GraphQL layer. The server must see writes in exactly the order of
// the user's actions, whatever the latency.
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { combineReducers, configureStore } from '@reduxjs/toolkit'
import createSagaMiddleware from 'redux-saga'
import { all, delay } from 'redux-saga/effects'
import type { LabelQueuePage, QueueItem } from './types'

type Call = { op: string; vars: Record<string, unknown> }
const calls: Call[] = []
let failNextSave = false

const item = (id: number): QueueItem => ({
  id,
  imageUrl: `images/sv_${id}_x.jpg`,
  latitude: 47.5,
  longitude: 19.05,
  streetViewUrl: 'https://example.invalid',
  reason: 'uncertain',
  area: 'budapest',
  cellLabels: 0,
  boundary: '2|3',
})

vi.mock('../graphql', () => ({
  // Documents are only used as keys here.
  gql: (source: string) => source,
  *gqlQuery(options: { query: string; variables?: Record<string, unknown> }) {
    yield delay(1)
    calls.push({ op: options.query.includes('labelExamples') ? 'examples' : 'queue', vars: options.variables ?? {} })
    if (options.query.includes('labelExamples')) return { labelExamples: [] }
    const page: LabelQueuePage = {
      strategy: 'MIXED',
      items: [1, 2, 3].map(item),
      stats: { totalLabelled: 10, labelledToday: 0, eligible: 3, scored: 3, rechecked: 0 },
    }
    return { labelQueue: page }
  },
  *gqlMutate(options: { mutation: string; variables: Record<string, unknown> }) {
    const isUndo = options.mutation.includes('undoQuickLabel')
    // The first save is slow: an un-ordered writer would let the undo overtake it.
    yield delay(calls.some(c => c.op === 'save') ? 5 : 40)
    calls.push({ op: isUndo ? 'undo' : 'save', vars: options.variables })
    if (!isUndo && failNextSave) {
      failNextSave = false
      throw new Error('db down')
    }
    return isUndo ? { undoQuickLabel: true } : { quickLabel: { pointId: 0, rqi: 0, totalLabelled: 0, labelledToday: 0 } }
  },
}))

const { default: reducer, actions } = await import('./slice')
const { default: sagas } = await import('./sagas')

const makeStore = () => {
  const sagaMiddleware = createSagaMiddleware()
  const store = configureStore({
    reducer: combineReducers({ labeling: reducer }),
    middleware: gdm => gdm({ serializableCheck: false }).concat(sagaMiddleware),
  })
  sagaMiddleware.run(function* () {
    yield all(sagas)
  })
  return store
}

const settle = (ms = 150) => new Promise(r => setTimeout(r, ms))

describe('label writer saga', () => {
  // Skips persist in localStorage (by design); isolate the tests.
  beforeEach(() => window.localStorage.clear())

  it('loads a page on entry, excluding nothing yet', async () => {
    calls.length = 0
    const store = makeStore()
    store.dispatch(actions.enter())
    await settle()
    expect(store.getState().labeling.queue.map(i => i.id)).toEqual([1, 2, 3])
    expect(calls.find(c => c.op === 'queue')?.vars).toMatchObject({ strategy: 'MIXED', excludeIds: [] })
  })

  it('sends rate, undo, re-rate of the same frame in order (slow first save)', async () => {
    calls.length = 0
    const store = makeStore()
    store.dispatch(actions.enter())
    await settle()
    calls.length = 0

    store.dispatch(actions.rate({ id: 1, rqi: 2 }))
    store.dispatch(actions.undoLast())
    store.dispatch(actions.rate({ id: 1, rqi: 4 }))
    store.dispatch(actions.rate({ id: 1, rqi: 3 })) // double tap: ignored
    await settle()

    const writes = calls.filter(c => c.op !== 'queue')
    expect(writes.map(c => c.op)).toEqual(['save', 'undo', 'save'])
    expect(writes[0].vars).toMatchObject({ input: { pointId: 1, rqi: 2, strategy: 'mixed', reason: 'uncertain' } })
    expect(writes[1].vars).toEqual({ pointId: 1 })
    expect(writes[2].vars).toMatchObject({ input: { pointId: 1, rqi: 4 } })
    expect(store.getState().labeling.outbox).toEqual([])
  })

  it('a skip is remembered by the next session (localStorage)', async () => {
    const first = makeStore()
    first.dispatch(actions.enter())
    await settle()
    first.dispatch(actions.skip({ id: 1 }))
    await settle()
    const second = makeStore()
    second.dispatch(actions.enter())
    await settle()
    expect(second.getState().labeling.queue.map(i => i.id)).toEqual([2, 3])
  })

  it('refills with every held frame excluded once the queue runs low', async () => {
    calls.length = 0
    const store = makeStore()
    store.dispatch(actions.enter())
    await settle()
    store.dispatch(actions.skip({ id: 1 }))
    await settle()
    const refill = calls.filter(c => c.op === 'queue')[1]
    expect(refill).toBeDefined()
    expect((refill.vars.excludeIds as number[]).sort()).toEqual([1, 2, 3])
  })

  it('a failed save returns the frame to the screen with an error', async () => {
    const store = makeStore()
    store.dispatch(actions.enter())
    await settle()
    failNextSave = true
    store.dispatch(actions.rate({ id: 1, rqi: 2 }))
    await settle()
    const s = store.getState().labeling
    expect(s.queue[0].id).toBe(1)
    expect(s.error).toContain('db down')
    expect(s.sessionRated).toBe(0)
  })
})
