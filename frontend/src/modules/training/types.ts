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


export interface AnnotationBox {
  x: number
  y: number
  w: number
  h: number
  label: 'pothole' | 'patch' | 'shadow' | 'cracks'
  id: string // Unique ID for keying
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
  annotations: AnnotationBox[]
  loading: boolean
  saving: boolean
  error: string | null
  brushSize: number // For future paint features, keeping it simple now
  selectedTool: 'pothole' | 'patch' | 'shadow' | 'cracks'
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
}
