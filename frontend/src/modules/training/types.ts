export interface TrainingPoint {
  id: number
  imageUrl?: string
  rqiScore?: number
  manualRqi?: number
  manualTags?: string[]
  createdAt: string
  latitude: number
  longitude: number
}

export type DamageLabel =
  | 'long_crack'
  | 'trans_crack'
  | 'alligator_crack'
  | 'pothole'
  | 'patch'
  | 'degradation'
  | 'shadow'
  | 'manhole'
  | 'marking'
  | 'ignore'
  | 'edit' // Special tool for editing existing polygons

export interface Annotation {
  id: string
  label: DamageLabel
  type: 'box' | 'polygon'
  // For box
  x?: number
  y?: number
  w?: number
  h?: number
  // For polygon
  points?: [number, number][]
  score?: number
}

export interface TrainingStats {
  total: number
  pending: number
  annotated: number
  avgRqi: number
  goodCount: number
  fairCount: number
  poorCount: number
  pendingAnalysis: number
}

export interface TrainingState {
  imageId: string | null
  imageUrl: string | null
  annotations: Annotation[]
  loading: boolean
  saving: boolean
  error: string | null
  brushSize: number
  selectedTool: DamageLabel
  manualRqi: number | null
  tags: string[]
  manualComment: string
  lastSavedSettings: {
    rqi: number | null
    tags: string[]
    comment: string
  } | null

  // Job Tracking
  analysisJobId: string | null
  analysisProgress: number
  analysisTotal: number
  analysisStatus: 'idle' | 'running' | 'completed' | 'failed' | 'cancelled'
  analysisMessage: string

  trainingStatus: 'idle' | 'running' | 'completed' | 'failed' | 'cancelled'

  // Navigation & List Cache
  navigationIds: string[]
  items: TrainingPoint[]

  // Pagination & Stats
  totalCount: number
  hasMore: boolean
  offset: number
  activeMode: 'pending' | 'reviewed' | 'all'
  globalStats: TrainingStats | null

  // Export metadata (e.g. for Google Colab)
  exports?: {
    notebookPath?: string
    datasetPath?: string
    instructions?: string
  } | null
  autoDetectConf: number // Local override for magic wand sensitivity
  autoDetectClasses: string[] // Classes to filter for auto-detection
}
