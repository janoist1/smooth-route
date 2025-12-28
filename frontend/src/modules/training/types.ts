export interface AnnotationBox {
  x: number
  y: number
  w: number
  h: number
  label: 'pothole' | 'patch' | 'shadow' | 'cracks'
  id: string // Unique ID for keying
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
}
