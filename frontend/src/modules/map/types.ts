export interface RoadPoint {
  id: number
  latitude: number
  longitude: number
  rqi_score?: number
  heading: number
}

export interface RoadPointDetail extends RoadPoint {
  image_url: string
  image_path?: string
  damage_count: number
  damage_types?: Record<string, number>
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  analysis_metadata?: any
  created_at: string
}

export interface MapState {
  points: RoadPoint[]
  loading: boolean
  error: string | null
  selectedPointId: number | null
  selectedPointDetail: RoadPointDetail | null
  loadingDetail: boolean
  viewport: {
    center: [number, number]
    zoom: number
  }
  // Route Planner
  routePoints: [number, number][] | null
  isPlanningRoute: boolean
  isAnalyzingRoute: boolean
  routeAnalysisJobId: string | null
  // Form State
  origin: string
  destination: string
  pickingLocationFor: 'origin' | 'destination' | null
}
