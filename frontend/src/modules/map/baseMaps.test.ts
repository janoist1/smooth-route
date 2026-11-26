import { describe, it, expect } from 'vitest'
import { BASE_MAPS } from './baseMaps'

describe('base maps', () => {
  it('uses no CARTO tiles (they now need an API key and show a placeholder)', () => {
    for (const map of Object.values(BASE_MAPS)) {
      expect(map.url).not.toMatch(/cartocdn|carto\.com/)
      expect(map.attribution).not.toMatch(/CARTO/)
    }
  })

  it('credits OpenStreetMap on every style (road segments are OSM data too)', () => {
    for (const map of Object.values(BASE_MAPS)) {
      expect(map.attribution).toContain('https://www.openstreetmap.org/copyright')
    }
  })

  it('serves OSM tiles from the single-host URL, recoloured for dark and light', () => {
    expect(BASE_MAPS.street.url).toBe('https://tile.openstreetmap.org/{z}/{x}/{y}.png')
    expect(BASE_MAPS.dark).toMatchObject({ url: BASE_MAPS.street.url, className: 'basemap-dark' })
    expect(BASE_MAPS.light).toMatchObject({ url: BASE_MAPS.street.url, className: 'basemap-light' })
  })
})
