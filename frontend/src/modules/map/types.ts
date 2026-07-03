export interface RoadPoint {
  id: number
  latitude: number
  longitude: number
  rqi_score?: number
  dino_rqi_score?: number
  dino_score?: number
  dino_p_bad?: number
  manual_rqi?: number
  rqi_source?: string
  heading?: number
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

import type { QualityGrid } from './aggregation'

export interface MapState {
  points: RoadPoint[]
  // Zoomed-out overview: average-RQI grid cells (null until fetched).
  grid: QualityGrid | null
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
