// Pure helpers for the quick-rate screen (unit-tested in logic.test.ts).
import { RQI_LEVELS, rqiLevel } from '../ui'
import type { RqiLevel } from '../ui'
import type { HistoryEntry, LabelStrategy, QueueItem } from './types'

/**
 * The rating buttons, best → worst: names, colours, rubric text and numeric
 * values all come from the canonical scale (shared/rqi_scale.json via
 * modules/ui rqiScale). Nothing about the scale is hard-coded on this page,
 * so a change of levels or numeric direction there needs no change here.
 */
export const RATING_LEVELS: readonly RqiLevel[] = RQI_LEVELS

/** The scale level for a stored / predicted value (undefined when unknown). */
export const levelOf = (value: number | null | undefined): RqiLevel | undefined =>
  value == null ? undefined : rqiLevel(value)

const levelValues = RATING_LEVELS.map(l => l.value)
/** "1–5": the digit keys that rate, as shown in the help text. */
export const RATING_KEY_RANGE = `${Math.min(...levelValues)}–${Math.max(...levelValues)}`

export const STRATEGIES: { value: LabelStrategy; label: string; hint: string }[] = [
  { value: 'MIXED', label: 'Vegyes', hint: 'Felváltva új helyek és bizonytalan képek' },
  { value: 'DIVERSE', label: 'Új helyek', hint: 'Címkézetlen 1 km-es cellák, Budapest elöl' },
  { value: 'UNCERTAIN', label: 'Bizonytalan', hint: 'Ahol a modell két szint határán áll' },
  {
    value: 'RECHECK',
    label: 'Újraellenőrzés',
    hint: 'Régi címkék újra, vakon (a régi érték rejtve): előbb a gyanúsak, aztán véletlen minta',
  },
]

export const QUEUE_BATCH = 20
export const REFILL_AT = 8
export const PREFETCH_AHEAD = 4
export const HISTORY_LIMIT = 50
export const SKIP_MEMORY = 2000

const AREA_LABELS: Record<string, string> = {
  budapest: 'Budapest',
  torokbalint: 'Törökbálint–Budaörs',
  szekesfehervar: 'Székesfehérvár',
  tapolca: 'Tapolca',
  other: 'Új terület',
}

export const areaLabel = (area: string): string => AREA_LABELS[area] ?? area

/** A labelled frame served again by the re-check strategy (not a new label). */
export const isRecheckItem = (item: Pick<QueueItem, 'reason'>): boolean => item.reason.startsWith('recheck')

/** Short Hungarian chip: why this frame is in the queue. */
export const reasonLabel = (item: Pick<QueueItem, 'reason' | 'area' | 'cellLabels' | 'boundary'>): string => {
  if (item.reason === 'recheck_suspicious') return 'Újraellenőrzés · gyanús'
  if (item.reason === 'recheck_sample') return 'Újraellenőrzés · minta'
  if (item.reason === 'uncertain') {
    return item.boundary ? `Bizonytalan · ${item.boundary} határ` : 'Bizonytalan'
  }
  const where = areaLabel(item.area)
  return item.cellLabels === 0 ? `Új cella · ${where}` : `Ritka cella · ${where}`
}

export type KeyAction =
  | { type: 'rate'; rqi: number }
  | { type: 'skip' }
  | { type: 'undo' }
  | { type: 'reveal' }
  | { type: 'zoom' }
  | null

/** Desktop shortcuts: a level's number rates it, → / S skip, ← / Backspace / Z undo, M model, Space zoom. */
export const keyToAction = (
  key: string,
  modifiers: { ctrlKey?: boolean; metaKey?: boolean; altKey?: boolean } = {},
): KeyAction => {
  if (modifiers.ctrlKey || modifiers.metaKey || modifiers.altKey) return null
  if (/^\d$/.test(key) && levelOf(Number(key))) return { type: 'rate', rqi: Number(key) }
  switch (key) {
    case 'ArrowRight':
    case 's':
    case 'S':
      return { type: 'skip' }
    case 'ArrowLeft':
    case 'Backspace':
    case 'z':
    case 'Z':
      return { type: 'undo' }
    case 'm':
    case 'M':
      return { type: 'reveal' }
    case ' ':
      return { type: 'zoom' }
    default:
      return null
  }
}

/** Ids the server must not serve again: queued, rated or skipped here. */
export const excludeIds = (queue: QueueItem[], history: HistoryEntry[], skipped: number[]): number[] => {
  const ids = new Set<number>()
  queue.forEach(it => ids.add(it.id))
  history.forEach(h => ids.add(h.item.id))
  skipped.forEach(id => ids.add(id))
  return [...ids]
}

/** Append incoming items that are not already queued, rated or skipped. */
export const mergeQueue = (queue: QueueItem[], incoming: QueueItem[], blocked: Iterable<number>): QueueItem[] => {
  const seen = new Set<number>(blocked)
  queue.forEach(it => seen.add(it.id))
  const fresh: QueueItem[] = []
  for (const it of incoming) {
    if (seen.has(it.id)) continue
    seen.add(it.id)
    fresh.push(it)
  }
  return fresh.length ? [...queue, ...fresh] : queue
}

export const needsRefill = (queueLength: number, loading: boolean, exhausted: boolean): boolean =>
  !loading && !exhausted && queueLength < REFILL_AT

/** Same-origin image path (the dev server proxies /images to the backend). */
export const imageSrc = (url: string): string => (url.startsWith('/') || url.startsWith('http') ? url : `/${url}`)

/** Images to warm the browser cache with: the frames after the current one. */
export const prefetchUrls = (queue: QueueItem[], ahead: number = PREFETCH_AHEAD): string[] =>
  queue.slice(1, 1 + ahead).map(it => imageSrc(it.imageUrl))

export const pushHistory = (history: HistoryEntry[], entry: HistoryEntry, limit = HISTORY_LIMIT): HistoryEntry[] => {
  const next = [...history, entry]
  return next.length > limit ? next.slice(next.length - limit) : next
}

/** Anything in the history can be undone (an in-flight save is awaited first). */
export const canUndo = (history: HistoryEntry[]): boolean => history.length > 0

/** Street View capture month ("YYYY-MM") older than `years` (default 4, as on the map). */
export const isOldCapture = (ym: string | null | undefined, now: Date = new Date(), years = 4): boolean => {
  const m = /^(\d{4})-(\d{2})$/.exec(ym ?? '')
  if (!m) return false
  const months = (now.getFullYear() - Number(m[1])) * 12 + (now.getMonth() + 1 - Number(m[2]))
  return months > years * 12
}

/** "67% azonos · 95% ±1 (n=12)" — the owner's agreement with their old labels. */
export const consistencyText = (
  stats: { rechecked: number; recheckSame?: number | null; recheckWithinOne?: number | null } | null,
): string | null => {
  if (!stats || !stats.rechecked || stats.recheckSame == null || stats.recheckWithinOne == null) return null
  const pct = (x: number) => `${Math.round(x * 100)}%`
  return `${pct(stats.recheckSame)} azonos · ${pct(stats.recheckWithinOne)} ±1 (n=${stats.rechecked})`
}

/** Human-agreement summary after rating: "egyezik" / "±1" / "eltér". */
export const agreement = (human: number, model: number | null | undefined): 'same' | 'near' | 'far' | null => {
  if (model == null) return null
  const d = Math.abs(human - model)
  return d === 0 ? 'same' : d === 1 ? 'near' : 'far'
}

// --- per-browser memory (try/catch: private mode, blocked storage) ---------

const SKIPPED_KEY = 'quickLabel.skipped'
const STRATEGY_KEY = 'quickLabel.strategy'

export const loadSkipped = (): number[] => {
  try {
    const raw = window.localStorage.getItem(SKIPPED_KEY)
    const parsed: unknown = raw ? JSON.parse(raw) : []
    return Array.isArray(parsed) ? parsed.filter((x): x is number => Number.isInteger(x)) : []
  } catch {
    return []
  }
}

export const saveSkipped = (ids: number[]): void => {
  try {
    window.localStorage.setItem(SKIPPED_KEY, JSON.stringify(ids.slice(-SKIP_MEMORY)))
  } catch {
    // storage unavailable: skips are then remembered for this tab only
  }
}

export const loadStrategy = (): LabelStrategy => {
  try {
    const raw = window.localStorage.getItem(STRATEGY_KEY)
    return STRATEGIES.some(s => s.value === raw) ? (raw as LabelStrategy) : 'MIXED'
  } catch {
    return 'MIXED'
  }
}

export const saveStrategy = (strategy: LabelStrategy): void => {
  try {
    window.localStorage.setItem(STRATEGY_KEY, strategy)
  } catch {
    // ignore
  }
}
