import { useEffect, useRef } from 'react'
import { useMap } from 'react-leaflet'
import L from 'leaflet'
import { getRQIColor } from '../../ui'
import type { QualityGrid } from '../aggregation'
import { GRID_FILL_OPACITY } from '../aggregation'

/**
 * Road-quality grid, drawn on a single canvas over the overlay pane.
 *
 * Each populated cell is filled with the colour of its AVERAGE RQI — colour
 * means quality, not density (unlike an additive heatmap, where overlapping
 * points would light up a busy-but-good road). Coverage is shown by which
 * cells are filled. One canvas keeps it fast for thousands of cells.
 */
export const QualityGridLayer: React.FC<{ grid: QualityGrid }> = ({ grid }) => {
  const map = useMap()
  const canvasRef = useRef<HTMLCanvasElement | null>(null)

  useEffect(() => {
    const canvas = L.DomUtil.create('canvas', 'leaflet-quality-grid') as HTMLCanvasElement
    canvas.style.position = 'absolute'
    canvas.style.pointerEvents = 'none'
    map.getPanes().overlayPane.appendChild(canvas)
    canvasRef.current = canvas

    const draw = () => {
      const ctx = canvas.getContext('2d')
      if (!ctx) return
      const size = map.getSize()
      // Anchor the canvas to the current top-left in layer coordinates so it
      // rides along with the pane transform during a drag; redraw on move end.
      const topLeft = map.containerPointToLayerPoint([0, 0])
      L.DomUtil.setPosition(canvas, topLeft)
      canvas.width = size.x
      canvas.height = size.y

      ctx.clearRect(0, 0, size.x, size.y)
      ctx.globalAlpha = GRID_FILL_OPACITY
      const { cell, cells } = grid
      for (let i = 0; i < cells.length; i++) {
        const [swLat, swLng, avgRqi] = cells[i]
        const p1 = map.latLngToContainerPoint([swLat, swLng])
        const p2 = map.latLngToContainerPoint([swLat + cell, swLng + cell])
        const x = Math.min(p1.x, p2.x)
        const y = Math.min(p1.y, p2.y)
        // +1px avoids hairline seams between adjacent cells.
        const w = Math.abs(p2.x - p1.x) + 1
        const h = Math.abs(p2.y - p1.y) + 1
        ctx.fillStyle = getRQIColor(avgRqi)
        ctx.fillRect(x, y, w, h)
      }
    }

    draw()
    map.on('moveend zoomend viewreset resize', draw)
    return () => {
      map.off('moveend zoomend viewreset resize', draw)
      // canvas.remove() is a no-op if the pane is already gone (map teardown
      // on navigation), unlike overlayPane.removeChild which would throw.
      canvas.remove()
      canvasRef.current = null
    }
  }, [map, grid])

  return null
}

export default QualityGridLayer
