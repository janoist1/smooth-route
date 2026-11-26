/** GraphQL enum LabelQueueStrategy (codegen: enumsAsTypes). */
export type LabelStrategy = 'MIXED' | 'UNCERTAIN' | 'DIVERSE' | 'RECHECK'

/** One frame served by the backend label queue (`labelQueue`). */
export interface QueueItem {
  id: number
  imageUrl: string
  latitude: number
  longitude: number
  heading?: number | null
  captureDate?: string | null
  streetViewUrl: string
  /** "diverse" | "uncertain" — why the queue picked this frame. */
  reason: string
  /** budapest | torokbalint | szekesfehervar | tapolca | other */
  area: string
  uncertainty?: number | null
  cellLabels: number
  /** Nearest decision boundary of the model score, e.g. "2|3". */
  boundary?: string | null
  /** The model's guess — hidden until the frame is rated (anchoring bias). */
  modelScore?: number | null
  modelRqi?: number | null
  modelPBad?: number | null
}

export interface QueueStats {
  totalLabelled: number
  labelledToday: number
  eligible: number
  scored: number
  /** Owner's self-consistency on re-checked frames (original vs re-check). */
  rechecked: number
  recheckSame?: number | null
  recheckWithinOne?: number | null
}

export interface LabelQueuePage {
  strategy: LabelStrategy
  items: QueueItem[]
  stats: QueueStats
}

/** Rubric thumbnail: a clear, already-labelled exemplar of one RQI class. */
export interface LabelExample {
  rqi: number
  id: number
  imageUrl: string
}

export type HistoryEntry =
  | {
      kind: 'rated'
      /** Matches the outbox write that stores this rating. */
      seq: number
      item: QueueItem
      rqi: number
      status: 'saving' | 'saved'
      revealed: boolean
      /** A new label (false for a re-check, which only replaces one). */
      isNew: boolean
    }
  | { kind: 'skipped'; item: QueueItem }

/** A server write waiting to be sent (in order) by the label writer saga. */
export type OutboxWrite =
  | {
      seq: number
      kind: 'save'
      id: number
      rqi: number
      reason: string
      revealed: boolean
      strategy: LabelStrategy
      elapsedMs?: number
    }
  | { seq: number; kind: 'undo'; id: number }

export interface LastResult {
  item: QueueItem
  rqi: number
}

export interface LabelingState {
  strategy: LabelStrategy
  /** queue[0] is the frame on screen. */
  queue: QueueItem[]
  /** Most recent last; undo pops from the end. */
  history: HistoryEntry[]
  /** Skipped frame ids, remembered across reloads (localStorage). */
  skipped: number[]
  sessionRated: number
  stats: QueueStats | null
  examples: LabelExample[]
  loading: boolean
  /** The last refill returned nothing new: this strategy has run dry. */
  exhausted: boolean
  error: string | null
  /** Show the model's guess on the current frame before rating (off by default). */
  reveal: boolean
  /** The frame just rated, for the after-rating model comparison. */
  lastResult: LastResult | null
  /** Label writes (saves + undos) not yet acknowledged by the server, oldest first. */
  outbox: OutboxWrite[]
  nextSeq: number
}

export type RateArgs = { id: number; rqi: number; elapsedMs?: number }
