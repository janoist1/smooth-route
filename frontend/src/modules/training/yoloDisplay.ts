// YOLO defect-polygon display rule (Era 14 / T-73): the owner-trained YOLO is
// overfit (held-out mask mAP50 0.26), so its polygons are shown from
// confidence 0.5 by default and always marked as indicative. Mirrors
// backend/config/analysis_settings.json "yolo_display_conf".
import type { Annotation } from './types'

export const YOLO_DISPLAY_CONF = 0.5

export const YOLO_INDICATIVE_NOTE_HU =
  'Tájékoztató jellegű: a hibafelismerő modell még kevés jelölt képből tanult.'

/** True when any polygon on the canvas is an AI (YOLO) suggestion, i.e. carries a score. */
export const hasAiSuggestions = (annotations: readonly Pick<Annotation, 'score'>[]): boolean =>
  annotations.some(a => typeof a.score === 'number')
