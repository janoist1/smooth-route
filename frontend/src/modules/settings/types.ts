export interface SystemSetting {
  key: string
  value: string | number
  description?: string
  explanation?: string
  category?: string
}

/** Read-only card describing the live RQI (DINO) artifact. */
export interface RqiModelInfo {
  available: boolean
  version?: number | null
  backbone?: string | null
  recipe?: string | null
  head?: string | null
  nTrain?: number | null
  qwk?: number | null
  mae?: number | null
  exactAcc?: number | null
  badRoadAcc?: number | null
  badRoadAuc?: number | null
  scaleMeaning?: string | null
  /** 'spatial_cv' (honest, ml/model_card.json) | 'artifact' (the file's own cv_metrics). */
  metricsSource?: string | null
  metricsProtocol?: string | null
  metricsMeasuredOn?: string | null
  /** QWK on ~200 m road segments (the map's unit). */
  segmentQwk?: number | null
  segmentLengthM?: number | null
  /** QWK with a whole collection area left out of training (a new region). */
  newAreaQwk?: number | null
}
