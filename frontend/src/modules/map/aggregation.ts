// Client-side policy for the zoom-based road-quality grid overview.
// Pure/config values so they can be unit-tested; the grid + averages are
// computed server-side (roadQualityGrid). GRID_MAX_ZOOM must match the backend
// constant in app/services/map_aggregation.py.

/** One grid cell: [swLat, swLng, avgRqi] — south-west corner + average RQI. */
export type QualityCell = [number, number, number]

/** Server payload: the cell size (degrees) and the populated cells. */
export interface QualityGrid {
  cell: number
  cells: QualityCell[]
}

export const GRID_MAX_ZOOM = 14

/** Below the threshold we render the quality grid; at/above it, individual points. */
export const shouldShowGrid = (zoom: number): boolean => zoom < GRID_MAX_ZOOM

/** Fill opacity for grid cells — translucent so base map labels show through. */
export const GRID_FILL_OPACITY = 0.55
