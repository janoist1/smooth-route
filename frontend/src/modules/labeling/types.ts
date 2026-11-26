/** GraphQL enum LabelQueueStrategy (codegen: enumsAsTypes). */
export type LabelStrategy = 'MIXED' | 'UNCERTAIN' | 'DIVERSE' | 'RECHECK' | 'SPRINT'

/** 'rate' = one frame, absolute grade; 'pair' = which of two is worse. */
export type LabelMode = 'rate' | 'pair'
export type PairResult = 'A' | 'B' | 'EQUAL'

export interface PairItem {
  a: QueueItem
  b: QueueItem
  scoreGap: number
}

export interface PairHistoryEntry {
  pair: PairItem
  result: PairResult
  clientId: string
}

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
  /** New labels made in sprint mode, toward sprintTarget. */
  sprintLabelled?: number
  sprintTarget?: number
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
      isSprint?: boolean
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
  /** Client-only link: a failed save must drop only its own queued undo. */
  | { seq: number; kind: 'undo'; id: number; saveSeq: number }
  | { seq: number; kind: 'pair'; clientId: string; aId: number; bId: number; result: PairResult; elapsedMs?: number }
  | { seq: number; kind: 'pairUndo'; clientId: string }

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
  mode: LabelMode
  /** pairs[0] is on screen. */
  pairs: PairItem[]
  pairHistory: PairHistoryEntry[]
  pairsLoading: boolean
  pairsExhausted: boolean
  pairsJudged: number
  /** Write sequence at a safe pair-page request start; null while saves are pending. */
  pairsFetchSeq: number | null
  /** Highest retrain milestone (every RETRAIN_EVERY sprint labels) already acknowledged. */
  retrainAck: number
}

export type RateArgs = { id: number; rqi: number; elapsedMs?: number }
