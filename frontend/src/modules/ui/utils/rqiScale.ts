// Canonical RQI scale for the UI. Source of truth: shared/rqi_scale.json (see
// shared/README.md). rqiScale.json next to this file is a byte-identical copy
// (scripts/sync_rqi_scale.py), because Vite only bundles frontend/. The copy is
// checked against the shared file in rqiScale.test.ts.
//
// This mirrors backend/app/core/rqi_scale.py. Write scale logic through these
// helpers, never as bare numbers (`<= 2`, `>= 3`, `[1, 2, 3, 4]` …), so a
// direction flip (1 = best ↔ 5 = best) is a change to the JSON only.
import raw from './rqiScale.json'

export type RqiDirection = 'lower_is_better' | 'higher_is_better'
export type RqiLevelKey = 'excellent' | 'good' | 'fair' | 'poor' | 'very_poor'

export interface RqiLevel {
  value: number
  key: RqiLevelKey
  label_hu: string
  label_en: string
  color: string
  rubric_hu: string
  rubric_en: string
}

export interface RqiScaleDefinition {
  name: string
  version: number
  direction: RqiDirection
  bad_from: number
  model_levels: number[]
  /** Labelling rule shown with the rubric (surface only, not speed limit / road class). */
  rubric_note_hu: string
  rubric_note_en: string
  levels: RqiLevel[]
  unknown: { label_hu: string; label_en: string; color: string }
}

/** The orientation models, YOLO bands and tuned cut-points are expressed in (1 = best). */
export const SEVERITY: RqiDirection = 'lower_is_better'

const parse = (data: unknown): RqiScaleDefinition => {
  const d = data as RqiScaleDefinition
  if (d.direction !== 'lower_is_better' && d.direction !== 'higher_is_better') {
    throw new Error(`rqi scale: bad direction ${String(d.direction)}`)
  }
  const values = d.levels.map(l => l.value).sort((a, b) => a - b)
  if (!values.every((v, i) => v === values[0] + i)) {
    throw new Error(`rqi scale: level values must be consecutive, got ${values.join(',')}`)
  }
  if (!values.includes(d.bad_from)) throw new Error('rqi scale: bad_from is not a level')
  return d
}

export const RQI_SCALE: RqiScaleDefinition = parse(raw)

const lowerIsBetter = RQI_SCALE.direction === 'lower_is_better'
const sortedValues = RQI_SCALE.levels.map(l => l.value).sort((a, b) => a - b)
const MIN = sortedValues[0]
const MAX = sortedValues[sortedValues.length - 1]
const byValue = new Map(RQI_SCALE.levels.map(l => [l.value, l]))
const byKey = new Map(RQI_SCALE.levels.map(l => [l.key, l]))

/** Levels best → worst, whatever the numeric direction. */
export const RQI_LEVELS: readonly RqiLevel[] = [...RQI_SCALE.levels].sort((a, b) =>
  lowerIsBetter ? a.value - b.value : b.value - a.value,
)
/** Levels the model can output, best → worst (5 / Nagyon rossz is never predicted). */
export const RQI_MODEL_LEVELS: readonly number[] = RQI_LEVELS.map(l => l.value).filter(v =>
  RQI_SCALE.model_levels.includes(v),
)
export const RQI_BAD_FROM = RQI_SCALE.bad_from
export const RQI_UNKNOWN = RQI_SCALE.unknown
export const RQI_RUBRIC_NOTE_HU = RQI_SCALE.rubric_note_hu

/** Numeric value of a level key, e.g. rqiValue('fair'). */
export const rqiValue = (key: RqiLevelKey): number => {
  const level = byKey.get(key)
  if (!level) throw new Error(`unknown RQI level key ${key}`)
  return level.value
}

/** The level for an exact integer value, or undefined. */
export const rqiLevel = (value: number): RqiLevel | undefined => byValue.get(value)

// ----- orientation -------------------------------------------------------

/** Mirror a value on the scale (6 − x on 1–5). */
export const flipRqi = (x: number): number => MIN + MAX - x
/** Severity (1 = best) value → canonical value. Identity while 1 = best. */
export const fromSeverity = (x: number): number => (RQI_SCALE.direction === SEVERITY ? x : flipRqi(x))
/** Canonical value → severity (1 = best). */
export const toSeverity = (x: number): number => (RQI_SCALE.direction === SEVERITY ? x : flipRqi(x))

// ----- ordering -----------------------------------------------------------

export const atOrBetter = (x: number, ref: number): boolean => (lowerIsBetter ? x <= ref : x >= ref)
export const atOrWorse = (x: number, ref: number): boolean => (lowerIsBetter ? x >= ref : x <= ref)
export const betterThan = (x: number, ref: number): boolean => (lowerIsBetter ? x < ref : x > ref)
export const worseThan = (x: number, ref: number): boolean => (lowerIsBetter ? x > ref : x < ref)
/** "Bad road": at or worse than bad_from — the event P(bad) predicts. */
export const isBadRqi = (x: number): boolean => atOrWorse(x, RQI_BAD_FROM)
/** Array.sort comparator: worst road first. */
export const compareWorstFirst = (a: number, b: number): number => toSeverity(b) - toSeverity(a)
/** Comparison sign for display, e.g. `RQI ${RQI_AT_OR_BETTER_SIGN} 2`. */
export const RQI_AT_OR_BETTER_SIGN = lowerIsBetter ? '≤' : '≥'
export const RQI_AT_OR_WORSE_SIGN = lowerIsBetter ? '≥' : '≤'
export const RQI_WORSE_THAN_SIGN = lowerIsBetter ? '>' : '<'

// ----- continuous score → level ------------------------------------------

const clampInt = (k: number): number => Math.min(MAX, Math.max(MIN, k))

/** Nearest level, clamped; exact halves go to the better (default) or worse level. */
export const nearestRqiLevel = (score: number, ties: 'better' | 'worse' = 'better'): number => {
  const s = toSeverity(score)
  return fromSeverity(clampInt(ties === 'better' ? Math.ceil(s - 0.5) : Math.floor(s + 0.5)))
}

/** Round toward the worse level (2.01 → 3 today), clamped. */
export const towardWorseRqiLevel = (score: number): number => fromSeverity(clampInt(Math.ceil(toSeverity(score))))

/** Hungarian label of the nearest level (halves toward the better), "Nincs adat" when missing. */
export const rqiScoreLabelHu = (score?: number | null): string => {
  if (score === undefined || score === null || !Number.isFinite(score)) return RQI_UNKNOWN.label_hu
  return rqiLevel(nearestRqiLevel(score))?.label_hu ?? RQI_UNKNOWN.label_hu
}

/**
 * Readable text colour on top of an RQI fill (dark text on light levels such as
 * Közepes amber, white on dark ones such as Kiváló blue). WCAG relative luminance.
 */
export const rqiTextColor = (background: string): string => {
  const hex = background.replace('#', '')
  const full = hex.length === 3 ? hex.split('').map(c => c + c).join('') : hex
  const channel = (i: number) => {
    const c = parseInt(full.slice(i, i + 2), 16) / 255
    return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4
  }
  const luminance = 0.2126 * channel(0) + 0.7152 * channel(2) + 0.0722 * channel(4)
  return luminance > 0.3 ? '#111' : '#fff'
}
