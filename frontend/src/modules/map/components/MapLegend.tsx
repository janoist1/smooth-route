import React, { useState } from 'react'
import { getRQIColor } from '../../ui'
import { useMap } from '../hooks'
import { useRoadSegments } from '../segments/hooks'
import { rqiLabelHu } from '../segments/labels'
import { layersForZoom, segmentOpacity } from '../segments/style'
import { isCompactScreen } from '../screen'
import './roadCards.css'

const roadColor = (color: string) => ({ '--road-color': color }) as React.CSSProperties

// Classes 1 and 2 share a colour on the map, so they share a legend entry.
const QUALITY_CHIPS = [
  { label: `${rqiLabelHu(1)} / ${rqiLabelHu(2)}`, color: getRQIColor(1) },
  { label: rqiLabelHu(3), color: getRQIColor(3) },
  { label: rqiLabelHu(4), color: getRQIColor(4) },
  { label: rqiLabelHu(null), color: getRQIColor(null) },
]

const SAMPLE_COLOR = getRQIColor(1)

/** A short line sample drawn exactly like the map draws a segment. */
const LineSample: React.FC<{ opacity: number; dashed?: boolean }> = ({ opacity, dashed }) => (
  <svg width="34" height="8" viewBox="0 0 34 8" aria-hidden="true">
    <line
      x1="2"
      y1="4"
      x2="32"
      y2="4"
      stroke={SAMPLE_COLOR}
      strokeWidth="4"
      strokeOpacity={opacity}
      strokeLinecap={dashed ? 'butt' : 'round'}
      strokeDasharray={dashed ? '8 6' : undefined}
    />
  </svg>
)

/**
 * Map legend: quality colours, what the line styling says about confidence,
 * and the OpenStreetMap attribution for the road network. Collapsible so it
 * does not eat a phone screen or sit on the route planner of a short laptop
 * screen (it starts collapsed on both).
 */
export const MapLegend: React.FC = () => {
  const { viewport, routePoints } = useMap()
  // null = no choice made yet: open where there is room, and step aside while
  // a planned route's summary fills the left column. A click settles it.
  const [userOpen, setUserOpen] = useState<boolean | null>(null)
  const [roomy] = useState(() => !isCompactScreen())
  const open = userOpen ?? (roomy && !routePoints)
  const { segmentsSupported } = useRoadSegments()
  const layers = layersForZoom(viewport.zoom, segmentsSupported)

  return (
    <aside className="map-legend" aria-label="Jelmagyarázat">
      <button
        type="button"
        className="map-legend__toggle"
        aria-expanded={open}
        onClick={() => setUserOpen(!open)}>
        <span>Jelmagyarázat</span>
        <span aria-hidden="true">{open ? '▾' : '▸'}</span>
      </button>

      {open && (
        <div className="map-legend__body">
          <div>
            <div style={{ marginBottom: 4 }}>Útminőség (szín)</div>
            <div className="map-legend__chips">
              {QUALITY_CHIPS.map(chip => (
                <span key={chip.label} className="map-legend__chip" style={roadColor(chip.color)}>
                  {chip.label}
                </span>
              ))}
            </div>
          </div>

          {layers.segments ? (
            <div data-testid="legend-confidence">
              <div style={{ marginBottom: 4 }}>Megbízhatóság (vonal)</div>
              <div className="map-legend__line">
                <LineSample opacity={segmentOpacity(1)} />
                <span>erős, folytonos: megbízható becslés</span>
              </div>
              <div className="map-legend__line">
                <LineSample opacity={segmentOpacity(0.3)} />
                <span>halvány: bizonytalanabb</span>
              </div>
              <div className="map-legend__line">
                <LineSample opacity={segmentOpacity(0.15)} dashed />
                <span>szaggatott: alacsony (kevés vagy ellentmondó kép)</span>
              </div>
              <div style={{ marginTop: 4 }}>
                {layers.frames
                  ? 'A pontok az egyes képkockák – koppints rájuk a fotóért.'
                  : 'Koppints egy útszakaszra a részletekért.'}
              </div>
            </div>
          ) : (
            <div data-testid="legend-overview">
              {layers.grid
                ? 'Áttekintő nézet: a négyzetek színe a terület átlagos útminősége. Nagyíts rá az egyes utakért.'
                : 'A pontok az egyes képkockák – koppints rájuk a fotóért.'}
            </div>
          )}

          <div className="map-legend__attribution">
            Úthálózat:{' '}
            <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener noreferrer">
              © OpenStreetMap contributors
            </a>
          </div>
        </div>
      )}
    </aside>
  )
}

export default MapLegend
