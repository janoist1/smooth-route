import type { PayloadAction } from '@reduxjs/toolkit'
import { createSlice } from '@reduxjs/toolkit'
import { createSagaAction } from 'saga-toolkit'
import { loadSkipped, loadStrategy, mergeQueue, pushHistory, SKIP_MEMORY } from './logic'
import type { LabelExample, LabelingState, LabelQueuePage, LabelStrategy, QueueStats, RateArgs } from './types'

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
}

// Per-browser memory (strategy, skipped frames) is read once at start-up.
const startState = (): LabelingState => ({
  ...initialState,
  strategy: loadStrategy(),
  skipped: loadSkipped(),
})

/** Route entry: load the rubric and the first batch (sagas.ts). */
export const enter = createSagaAction<void>('labeling/enter')
export const fetchQueue = createSagaAction<LabelQueuePage>('labeling/fetchQueue')
export const fetchExamples = createSagaAction<LabelExample[]>('labeling/fetchExamples')

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
      state.queue.shift()
      state.history = pushHistory(state.history, {
        kind: 'rated',
        seq,
        item: current,
        rqi: action.payload.rqi,
        status: 'saving',
        revealed: state.reveal,
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
      bumpStats(state, +1) // server truth arrives with the next queue page
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
        state.outbox.push({ seq: state.nextSeq++, kind: 'undo', id: entry.item.id })
        state.sessionRated = Math.max(0, state.sessionRated - 1)
        bumpStats(state, -1)
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
      if (write?.kind === 'undo') {
        state.error = `A visszavonás nem sikerült, a címke megmaradt: ${action.payload.message}`
        return
      }
      // A failed save: put the frame back on screen so the rating is not lost silently.
      const idx = state.history.findIndex(h => h.kind === 'rated' && h.seq === action.payload.seq)
      if (idx >= 0) {
        const [entry] = state.history.splice(idx, 1)
        state.queue.unshift(entry.item)
        state.sessionRated = Math.max(0, state.sessionRated - 1)
        bumpStats(state, -1)
      }
      state.lastResult = null
      state.error = `Mentés sikertelen: ${action.payload.message}`
    },
    setStrategy(state, action: PayloadAction<LabelStrategy>) {
      if (state.strategy === action.payload) return
      state.strategy = action.payload
      // Keep the frame on screen; drop the rest of the old strategy's batch.
      state.queue = state.queue.slice(0, 1)
      state.exhausted = false
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
    builder.addCase(fetchExamples.fulfilled, (state, action: PayloadAction<LabelExample[]>) => {
      state.examples = action.payload || []
    })
  },
})

export const { rate, skip, undoLast, writeDone, writeFailed, setStrategy, toggleReveal, clearError } =
  slice.actions

export const actions = {
  ...slice.actions,
  enter,
  fetchQueue,
  fetchExamples,
}

export default slice.reducer
