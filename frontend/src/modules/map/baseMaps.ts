import type { MapStyle } from './components/MapStyleSwitcher'

// Base maps: keyless providers whose terms allow a small public,
// non-commercial site. CARTO's basemaps need an API key now (every tile is an
// "API KEY REQUIRED" image), so the dark and light styles are the OpenStreetMap
// standard tiles recoloured in the browser with a CSS filter (index.css).
// OSM tile usage policy: attribution shown, normal browser requests only
// (no bulk download / prefetch), https://operations.osmfoundation.org/policies/tiles/

// Required wherever OSM tiles or the OSM-derived road segments are drawn.
export const OSM_ATTRIBUTION =
  '&copy; <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener noreferrer">OpenStreetMap</a> contributors'

const OSM_TILES = 'https://tile.openstreetmap.org/{z}/{x}/{y}.png'

export interface BaseMap {
  url: string
  attribution: string
  maxZoom: number
  /** CSS class on the tile layer (recolouring filter), if any. */
  className?: string
}

export const BASE_MAPS: Record<MapStyle, BaseMap> = {
  dark: { url: OSM_TILES, attribution: OSM_ATTRIBUTION, maxZoom: 19, className: 'basemap-dark' },
  light: { url: OSM_TILES, attribution: OSM_ATTRIBUTION, maxZoom: 19, className: 'basemap-light' },
  satellite: {
    url: 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
    attribution: `&copy; Esri | roads: ${OSM_ATTRIBUTION}`,
    maxZoom: 19,
  },
  street: { url: OSM_TILES, attribution: OSM_ATTRIBUTION, maxZoom: 19 },
}
