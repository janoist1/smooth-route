// RQI (Road Quality Index): 1 = excellent … 5 = unusable — lower is better.
//
// Single source of truth for how an RQI score is presented across the UI
// (marker colour, quality label, and which model's score to show). Keep all
// RQI display decisions here so the map, detail card and lists stay consistent.

export type RqiDisplaySource = 'yolo' | 'dino' | 'both'

/** The two model scores a point can carry. */
export interface RqiScores {
  rqi_score?: number | null // YOLO defect-detection heuristic
  dino_rqi_score?: number | null // frozen DINOv2 + trained head
}

/** Resolved score to display, plus which model produced it. */
export interface ResolvedRqi {
  score?: number
  model: 'yolo' | 'dino'
  label: string
}

/** Marker / badge colour for a score (5-level scale). */
export const getRQIColor = (score?: number | null): string => {
  if (score === undefined || score === null) return '#888' // unknown
  if (score <= 2.0) return '#4ade80' // green   – good
  if (score <= 3.0) return '#facc15' // yellow  – fair
  if (score <= 4.0) return '#f87171' // red     – poor
  return '#ef4444' //                            dark red – very poor
}

/** Human-readable quality label for a score. */
export const getRQILabel = (score?: number | null): string => {
  if (score === undefined || score === null) return 'Unknown'
  if (score <= 1.5) return 'Excellent'
  if (score <= 2.5) return 'Good'
  if (score <= 3.5) return 'Fair'
  if (score <= 4.5) return 'Poor'
  return 'Critical'
}

/**
 * Decide which model's score to display for a point given the configured source.
 * 'dino' and 'both' prefer the DINO score and fall back to YOLO when it is
 * missing; 'yolo' always uses the YOLO score.
 */
export const resolveRqi = (point: RqiScores, source: RqiDisplaySource): ResolvedRqi => {
  const dino = point.dino_rqi_score
  const yolo = point.rqi_score
  const hasDino = dino !== undefined && dino !== null

  if ((source === 'dino' || source === 'both') && hasDino) {
    return { score: dino ?? undefined, model: 'dino', label: 'DINO' }
  }
  if (source === 'dino') {
    return { score: yolo ?? undefined, model: 'yolo', label: 'YOLO (Fallback)' }
  }
  return { score: yolo ?? undefined, model: 'yolo', label: 'YOLO' }
}
