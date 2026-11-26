import type { PayloadAction } from '@reduxjs/toolkit'
import { createSlice } from '@reduxjs/toolkit'
import { createSagaAction } from 'saga-toolkit'
import { isRecheckItem, loadRetrainAck, loadSkipped, loadStrategy, mergeQueue, pushHistory, SKIP_MEMORY } from './logic'
import type {
  LabelExample,
  LabelingState,
  LabelMode,
  LabelQueuePage,
  LabelStrategy,
  PairItem,
  PairResult,
  QueueStats,
  RateArgs,
} from './types'

export const initialState: LabelingState = {
  strategy: 'MIXED',
  queue: [],
  history: [],
  skipped: [],
  sessionRated: 0,
  stats: null,
  examples: [],
  loading: false,
  exhausted: false,
  error: null,
  reveal: false,
  lastResult: null,
  outbox: [],
  nextSeq: 1,
  mode: 'rate',
  pairs: [],
  pairHistory: [],
  pairsLoading: false,
  pairsExhausted: false,
  pairsJudged: 0,
  retrainAck: 0,
}

// Per-browser memory (strategy, skipped frames) is read once at start-up.
const startState = (): LabelingState => ({
  ...initialState,
  strategy: loadStrategy(),
  skipped: loadSkipped(),
  retrainAck: loadRetrainAck(),
})

/** Route entry: load the rubric and the first batch (sagas.ts). */
export const enter = createSagaAction<void>('labeling/enter')
export const fetchQueue = createSagaAction<LabelQueuePage>('labeling/fetchQueue')
export const fetchExamples = createSagaAction<LabelExample[]>('labeling/fetchExamples')
export const fetchPairs = createSagaAction<{ pairs: PairItem[]; judged: number }>('labeling/fetchPairs')

const bumpStats = (state: LabelingState, delta: number) => {
  if (!state.stats) return
  state.stats.totalLabelled = Math.max(0, state.stats.totalLabelled + delta)
  state.stats.labelledToday = Math.max(0, state.stats.labelledToday + delta)
}

const errorMessage = (action: unknown, fallback: string): string => {
  const err = (action as { error?: { message?: string } }).error
  return err?.message || fallback
}

/**
 * The screen is optimistic: rating, skipping and undo change the UI at once.
 * Server writes are appended to `outbox` and sent strictly in order by one
 * saga (sagas.ts), so "rate A=2, undo A, rate A=4" lands exactly like that.
 */
const slice = createSlice({
  name: 'labeling',
  initialState: startState,
  reducers: {
    /** Rate the frame on screen. `id` guards against a double tap rating the next frame. */
    rate(state, action: PayloadAction<RateArgs>) {
      const current = state.queue[0]
      if (!current || current.id !== action.payload.id) return
      const seq = state.nextSeq++
      const isNew = !isRecheckItem(current)
      state.queue.shift()
      state.history = pushHistory(state.history, {
        kind: 'rated',
        seq,
        item: current,
        rqi: action.payload.rqi,
        status: 'saving',
        revealed: state.reveal,
        isNew,
      })
      state.outbox.push({
        seq,
        kind: 'save',
        id: current.id,
        rqi: action.payload.rqi,
        reason: current.reason,
        revealed: state.reveal,
        strategy: state.strategy,
        elapsedMs: action.payload.elapsedMs,
      })
      state.sessionRated += 1
      if (isNew) bumpStats(state, +1) // server truth arrives with the next queue page
      state.lastResult = { item: current, rqi: action.payload.rqi }
      state.error = null
    },
    skip(state, action: PayloadAction<{ id: number }>) {
      const current = state.queue[0]
      if (!current || current.id !== action.payload.id) return
      state.queue.shift()
      state.history = pushHistory(state.history, { kind: 'skipped', item: current })
      state.skipped = [...state.skipped.filter(id => id !== current.id), current.id].slice(-SKIP_MEMORY)
      state.lastResult = null
    },
    /** Undo the last rating or skip: the frame is back on screen at once. */
    undoLast(state) {
      const entry = state.history.pop()
      if (!entry) return
      state.queue.unshift(entry.item)
      if (entry.kind === 'rated') {
        state.outbox.push({ seq: state.nextSeq++, kind: 'undo', id: entry.item.id, saveSeq: entry.seq })
        state.sessionRated = Math.max(0, state.sessionRated - 1)
        if (entry.isNew) bumpStats(state, -1)
      } else {
        state.skipped = state.skipped.filter(id => id !== entry.item.id)
      }
      state.lastResult = null
    },
    writeDone(state, action: PayloadAction<{ seq: number }>) {
      state.outbox = state.outbox.filter(w => w.seq !== action.payload.seq)
      const entry = state.history.find(h => h.kind === 'rated' && h.seq === action.payload.seq)
      if (entry && entry.kind === 'rated') entry.status = 'saved'
    },
    writeFailed(state, action: PayloadAction<{ seq: number; message: string }>) {
      const write = state.outbox.find(w => w.seq === action.payload.seq)
      state.outbox = state.outbox.filter(w => w.seq !== action.payload.seq)
      if (write?.kind === 'pair' || write?.kind === 'pairUndo') {
        state.error = `A páros döntés mentése nem sikerült: ${action.payload.message}`
        return
      }
      if (write?.kind === 'undo') {
        state.error = `A visszavonás nem sikerült, a címke megmaradt: ${action.payload.message}`
        return
      }
      // The writer is serial, so the paired undo is still queued. Drop it:
      // undoing a failed save could revert an older label already in the DB.
      // Match the save sequence, not the frame id: a later re-rate has its own undo.
      if (write?.kind === 'save') {
        state.outbox = state.outbox.filter(w => w.kind !== 'undo' || w.saveSeq !== write.seq)
      }
      // A failed save: put the frame back on screen so the rating is not lost silently.
      const idx = state.history.findIndex(h => h.kind === 'rated' && h.seq === action.payload.seq)
      if (idx >= 0) {
        const [entry] = state.history.splice(idx, 1)
        state.queue.unshift(entry.item)
        state.sessionRated = Math.max(0, state.sessionRated - 1)
        if (entry.kind === 'rated' && entry.isNew) bumpStats(state, -1)
      }
      state.lastResult = null
      state.error = `Mentés sikertelen: ${action.payload.message}`
    },
    setStrategy(state, action: PayloadAction<LabelStrategy>) {
      if (state.strategy === action.payload) return
      const crossesRecheck = state.strategy === 'RECHECK' || action.payload === 'RECHECK'
      state.strategy = action.payload
      // Keep the frame on screen and drop the rest of the old batch, unless
      // switching into/out of re-check: new and old labels never mix.
      state.queue = crossesRecheck ? [] : state.queue.slice(0, 1)
      state.exhausted = false
    },
    setMode(state, action: PayloadAction<LabelMode>) {
      state.mode = action.payload
      state.pairsExhausted = false
    },
    /** Judge the pair on screen. `aId` guards against a double tap judging the next one. */
    judgePair(state, action: PayloadAction<{ aId: number; result: PairResult; clientId: string; elapsedMs?: number }>) {
      const pair = state.pairs[0]
      if (!pair || pair.a.id !== action.payload.aId) return
      state.pairs.shift()
      const { result, clientId, elapsedMs } = action.payload
      state.pairHistory = [...state.pairHistory, { pair, result, clientId }].slice(-50)
      state.outbox.push({ seq: state.nextSeq++, kind: 'pair', clientId, aId: pair.a.id, bId: pair.b.id, result, elapsedMs })
      state.pairsJudged += 1
    },
    undoPair(state) {
      const last = state.pairHistory.pop()
      if (!last) return
      state.pairs.unshift(last.pair)
      state.outbox.push({ seq: state.nextSeq++, kind: 'pairUndo', clientId: last.clientId })
      state.pairsJudged = Math.max(0, state.pairsJudged - 1)
    },
    ackRetrain(state, action: PayloadAction<number>) {
      state.retrainAck = Math.max(state.retrainAck, action.payload)
    },
    toggleReveal(state) {
      state.reveal = !state.reveal
    },
    clearError(state) {
      state.error = null
    },
  },
  extraReducers: builder => {
    builder.addCase(fetchQueue.pending, state => {
      state.loading = true
    })
    builder.addCase(fetchQueue.fulfilled, (state, action: PayloadAction<LabelQueuePage>) => {
      state.loading = false
      const page = action.payload
      // Server counts are authoritative only when none of our writes is in flight.
      if (state.outbox.length === 0 || !state.stats) state.stats = page.stats as QueueStats
      if (page.strategy !== state.strategy) return // strategy changed meanwhile
      const blocked = [...state.history.map(h => h.item.id), ...state.skipped]
      const before = state.queue.length
      state.queue = mergeQueue(state.queue, page.items, blocked)
      state.exhausted = state.queue.length === before
    })
    builder.addCase(fetchQueue.rejected, (state, action) => {
      state.loading = false
      state.error = errorMessage(action, 'A sor betöltése sikertelen')
    })
    builder.addCase(fetchPairs.pending, state => {
      state.pairsLoading = true
    })
    builder.addCase(fetchPairs.fulfilled, (state, action: PayloadAction<{ pairs: PairItem[]; judged: number }>) => {
      state.pairsLoading = false
      const held = new Set<number>()
      state.pairs.forEach(p => held.add(p.a.id).add(p.b.id))
      const fresh = action.payload.pairs.filter(p => !held.has(p.a.id) && !held.has(p.b.id))
      state.pairs = [...state.pairs, ...fresh]
      state.pairsExhausted = fresh.length === 0
      if (state.outbox.every(w => w.kind !== 'pair' && w.kind !== 'pairUndo')) state.pairsJudged = action.payload.judged
    })
    builder.addCase(fetchPairs.rejected, (state, action) => {
      state.pairsLoading = false
      state.error = errorMessage(action, 'A párok betöltése sikertelen')
    })
    builder.addCase(fetchExamples.fulfilled, (state, action: PayloadAction<LabelExample[]>) => {
      state.examples = action.payload || []
    })
  },
})

export const {
  rate,
  skip,
  undoLast,
  writeDone,
  writeFailed,
  setStrategy,
  toggleReveal,
  clearError,
  setMode,
  judgePair,
  undoPair,
  ackRetrain,
} = slice.actions

export const actions = {
  ...slice.actions,
  enter,
  fetchQueue,
  fetchExamples,
  fetchPairs,
}

export default slice.reducer
