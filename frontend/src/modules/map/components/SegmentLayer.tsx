import { useEffect, useRef } from 'react'
import { useMap } from 'react-leaflet'
import L from 'leaflet'
import type { RoadSegment } from '../segments/types'
import {
  isStaleSegment,
  segmentCasingStyle,
  segmentStyle,
  selectionHaloStyle,
} from '../segments/style'

interface SegmentLayerProps {
  segments: RoadSegment[]
  zoom: number
  selected: RoadSegment | null
  /** "Dim old images" filter: fade segments whose newest image is stale. */
  dimStale: boolean
  /** False while a route location is being picked: clicks go to the map. */
  interactive: boolean
  onSelect: (segment: RoadSegment) => void
}

interface Entry {
  segment: RoadSegment
  /** The coloured, clickable line. */
  line: L.Polyline
  /** Dark outline under it (contrast on light base maps). */
  casing: L.Polyline
}

interface Look {
  zoom: number
  dimStale: boolean
}

const paint = (entry: Entry, look: Look, hovered = false) => {
  const style = segmentStyle(entry.segment, look.zoom, {
    hovered,
    dimmed: look.dimStale && isStaleSegment(entry.segment),
  })
  // Leaflet keeps a previous dashArray unless it is explicitly cleared.
  entry.line.setStyle({ dashArray: undefined, ...style })
  entry.casing.setStyle({ dashArray: undefined, ...segmentCasingStyle(style) })
}

/**
 * Road segments as coloured polylines: colour = quality class, opacity =
 * confidence, dashed = low confidence (rules in ../segments/style.ts).
 *
 * Managed imperatively (one effect builds all lines) instead of one React
 * component per segment — a city viewport can hold a few thousand segments and
 * they all share the map's canvas renderer.
 *
 * Draw order inside the shared canvas, bottom → top: [route], casings, other
 * segments, selection halo, selected segment, frame dots. The segment lines
 * are sent to the back whenever they change so the dots stay clickable on top;
 * the route is kept under them by MapView.
 */
const SegmentLayer: React.FC<SegmentLayerProps> = ({
  segments,
  zoom,
  selected,
  dimStale,
  interactive,
  onSelect,
}) => {
  const map = useMap()
  const entriesRef = useRef<Map<string, Entry>>(new Map())
  // Event handlers live as long as the lines; they read the current props here.
  const liveRef = useRef({ zoom, dimStale, interactive, onSelect })
  useEffect(() => {
    liveRef.current = { zoom, dimStale, interactive, onSelect }
  }, [zoom, dimStale, interactive, onSelect])

  // (Re)build the lines when the segment list changes.
  useEffect(() => {
    const group = L.layerGroup()
    const entries = new Map<string, Entry>()

    for (const segment of segments) {
      if (!segment.path || segment.path.length < 2) continue
      const casing = L.polyline(segment.path, { interactive: false })
      const line = L.polyline(segment.path)
      const entry: Entry = { segment, line, casing }
      paint(entry, liveRef.current)

      line.on('click', () => {
        const live = liveRef.current
        if (live.interactive) live.onSelect(segment)
      })
      line.on('mouseover', () => paint(entry, liveRef.current, true))
      line.on('mouseout', () => paint(entry, liveRef.current, false))

      group.addLayer(casing)
      group.addLayer(line)
      entries.set(segment.id, entry)
    }

    group.addTo(map)
    entriesRef.current = entries
    return () => {
      group.remove()
      entriesRef.current = new Map()
    }
  }, [map, segments])

  // Restyle in place when the zoom or the stale filter changes.
  useEffect(() => {
    entriesRef.current.forEach(entry => paint(entry, { zoom, dimStale }))
  }, [zoom, dimStale, segments])

  // Selection: white halo under the selected segment, drawn at full strength.
  // A segment picked from the route summary may not be in the viewport list —
  // then it gets its own line.
  useEffect(() => {
    const entries = entriesRef.current
    const extras: L.Polyline[] = []
    let selectedLine: L.Polyline | null = null

    if (selected && selected.path.length >= 2) {
      const halo = L.polyline(selected.path, { ...selectionHaloStyle(zoom), interactive: false })
      halo.addTo(map)
      extras.push(halo)

      selectedLine = entries.get(selected.id)?.line ?? null
      if (!selectedLine) {
        selectedLine = L.polyline(selected.path, { interactive: false }).addTo(map)
        extras.push(selectedLine)
      }
      selectedLine.setStyle({ dashArray: undefined, ...segmentStyle(selected, zoom), opacity: 1 })

      // Each call puts the layer at the very bottom: the selected line first,
      // then the halo under it, then everything else under both.
      selectedLine.bringToBack()
      halo.bringToBack()
    }
    entries.forEach(({ line }) => {
      if (line !== selectedLine) line.bringToBack()
    })
    entries.forEach(({ casing }) => casing.bringToBack())

    return () => {
      extras.forEach(layer => layer.remove())
      // Give a de-selected viewport line its normal look back.
      const entry = selected ? entriesRef.current.get(selected.id) : undefined
      if (entry) paint(entry, liveRef.current)
    }
  }, [map, segments, selected, zoom, dimStale])

  return null
}

export default SegmentLayer
