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
}
