import { describe, expect, it } from 'vitest'
import { routingAttribution } from './routingAttribution'
import L from 'leaflet'
import { OSM_ATTRIBUTION } from './baseMaps'

describe('route attribution', () => {
  it('credits OSRM and FOSSGIS with the required map repair link', () => {
    const attribution = routingAttribution('osm')
    expect(attribution).toContain('Útvonal: ')
    expect(attribution).toContain('OSRM')
    expect(attribution).toContain('FOSSGIS')
    expect(attribution).toContain('https://www.openstreetmap.org/fixthemap')
    expect(attribution).toContain('Térkép javítása')
  })

  it('uses the server-selected Google credit and never interpolates upstream HTML', () => {
    expect(routingAttribution('google')).toBe('Útvonal: Google Maps')
    expect(routingAttribution('<script>')).not.toContain('<script>')
  })

  it('adds and removes routing credit with a Leaflet layer while retaining OSM credit', () => {
    const container = document.createElement('div')
    const map = L.map(container).setView([47.5, 19.04], 13)
    try {
      L.layerGroup([], { attribution: OSM_ATTRIBUTION }).addTo(map)
      const route = L.layerGroup([], { attribution: routingAttribution('osm') }).addTo(map)
      const control = map.attributionControl.getContainer()!
      expect(control.textContent).toContain('OpenStreetMap')
      expect(control.textContent).toContain('FOSSGIS')
      expect(control.querySelector('a[href="https://www.openstreetmap.org/fixthemap"]')).not.toBeNull()
      route.remove()
      expect(control.textContent).toContain('OpenStreetMap')
      expect(control.textContent).not.toContain('FOSSGIS')
    } finally { map.remove() }
  })
})
