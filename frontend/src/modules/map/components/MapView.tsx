import React, { useEffect, useRef, useState } from 'react'
import { MapContainer, TileLayer, CircleMarker, Polyline, useMapEvents } from 'react-leaflet'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import { useMap } from '../hooks'
import { useRoadSegments } from '../segments/hooks'
import { layersForZoom, segmentWeight } from '../segments/style'
import { pathMidpoint } from '../segments/geometry'
import type { Bounds, RoadSegment } from '../segments/types'
import { isNarrowScreen } from '../screen'
import PointDetailCard from './PointDetailCard'
import SegmentDetailCard from './SegmentDetailCard'
import SegmentLayer from './SegmentLayer'
import MapStyleSwitcher from './MapStyleSwitcher'
import RoutePlanner from './RoutePlanner'
import type { MapStyle } from './MapStyleSwitcher'

import { getRQIColor, resolveRqi } from '../../ui'
import { useRqiDisplaySource } from '../../settings/hooks'
import QualityGridLayer from './QualityGridLayer'
import StaleImageToggle from './StaleImageToggle'
import { BASE_MAPS } from '../baseMaps'
import { isStaleCapture } from '../captureDate'

// Helper to handle map events
// Helper to handle map events
const MapEvents = ({
  onMove,
}: {
  onMove: (bbox: number[], center: [number, number], zoom: number) => void
}) => {
  const map = useMapEvents({
    moveend: () => {
      const bounds = map.getBounds()
      const bbox = [bounds.getWest(), bounds.getSouth(), bounds.getEast(), bounds.getNorth()]
      const center = map.getCenter()
      onMove(bbox, [center.lat, center.lng], map.getZoom())
    },
  })



  return null
}

// Controller to sync Redux -> Map (Guard against infinite loops)
const MapController = ({ viewport }: { viewport: { center: [number, number]; zoom: number } }) => {
  const map = useMapEvents({})

  useEffect(() => {
    const currentCenter = map.getCenter()
    const currentZoom = map.getZoom()

    const latDiff = Math.abs(currentCenter.lat - viewport.center[0])
    const lngDiff = Math.abs(currentCenter.lng - viewport.center[1])
    const zoomDiff = Math.abs(currentZoom - viewport.zoom)

    // Only update if difference is significant (precision issue protection)
    // Increased tolerance to 0.0005 (~50m) to prevent fighting with URL updates
    if (latDiff > 0.0005 || lngDiff > 0.0005 || zoomDiff > 0.5) {
      map.setView(viewport.center, viewport.zoom)
    }
  }, [viewport, map])

  return null
}

const MapClickHandler = () => {
    const { pickingLocationFor, updatePickedLocation } = useMap()
    const map = useMapEvents({
        click: (e) => {
            if (pickingLocationFor) {
                updatePickedLocation({ lat: e.latlng.lat, lng: e.latlng.lng })
            }
        }
    })
    
    useEffect(() => {
        if (pickingLocationFor) {
            map.getContainer().style.cursor = 'crosshair'
        } else {
            map.getContainer().style.cursor = ''
        }
    }, [pickingLocationFor, map])
    
    return null
}

// Fits the map to a segment when the route summary asks for it (one-shot
// request from the store; `seq` tells repeated requests apart).
const SegmentFocusController = ({
  focus,
  selected,
}: {
  focus: { bounds: Bounds; seq: number } | null
  selected: RoadSegment | null
}) => {
  const map = useMapEvents({})
  // Start at the current seq: a request already handled before this mount
  // (e.g. navigating away and back) must not move the map again.
  const handledSeq = useRef(focus?.seq ?? 0)

  // Phone: the segment card is a bottom sheet. A segment tapped in the lower
  // part of the map would end up under it, so slide it into the free area.
  useEffect(() => {
    if (!selected || !isNarrowScreen()) return
    if (focus && focus.seq !== handledSeq.current) return // a fit is about to run instead
    const mid = pathMidpoint(selected.path)
    if (!mid) return
    const height = map.getSize().y
    const y = map.latLngToContainerPoint([mid.lat, mid.lng]).y
    if (y > height * 0.36) map.panBy([0, Math.round(y - height * 0.22)])
  }, [selected, focus, map])

  useEffect(() => {
    if (!focus || focus.seq === handledSeq.current) return
    handledSeq.current = focus.seq
    const size = map.getSize()
    const narrow = isNarrowScreen()
    // Keep the segment clear of what covers the map: the bottom sheet on a
    // phone; the route planner (left) and the segment card (right) on a
    // screen wide enough to leave room between them.
    const sidePanels = !narrow && size.x >= 1000
    map.fitBounds(focus.bounds, {
      paddingTopLeft: [sidePanels ? 400 : 40, 90],
      paddingBottomRight: [sidePanels ? 360 : 40, narrow ? Math.round(size.y * 0.6) : 60],
      maxZoom: 17,
    })
  }, [focus, map])

  return null
}

interface MapViewProps {
  onTrain: (id: string | number) => void
  onMapMove: (bbox: number[], center: [number, number], zoom: number) => void
}

const MapView: React.FC<MapViewProps> = ({ onTrain, onMapMove }) => {
  const {
    points,
    grid,
    loading,
    selectPoint,
    selectedPointDetail,
    loadingDetail,
    viewport,
    routePoints,
    routeAlternatives,
    selectedRouteIndex,
    selectRouteAlternative,
    pickingLocationFor,
  } = useMap()
  const {
    segments,
    segmentsLoading,
    segmentsError,
    segmentsEmpty,
    segmentsSupported,
    selectedSegment,
    segmentFrames,
    segmentFocus,
    selectSegment,
  } = useRoadSegments()
  const [mapStyle, setMapStyle] = useState<MapStyle>('dark')
  // One canvas for every vector layer (segments, dots, route). The tolerance
  // widens the hit area so thin road lines can be tapped on a phone.
  const [renderer] = useState(() => L.canvas({ padding: 0.5, tolerance: 6 }))
  // Optional: dim points whose Street View image is old (quality may be outdated).
  const [dimStale, setDimStale] = useState(false)

  const displaySource = useRqiDisplaySource()

  // Which layers this zoom shows: grid (overview) -> road segments -> + frame dots.
  const layers = layersForZoom(viewport.zoom, segmentsSupported)
  // Below the dot zoom, frames only appear around the selected segment.
  const dots = layers.frames ? points : layers.segments && selectedSegment ? segmentFrames : []
  const pointCardOpen = Boolean(selectedPointDetail || loadingDetail)

  // Keyboard: Escape closes the open card (point card first, then segment).
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== 'Escape') return
      if (pointCardOpen) selectPoint(null)
      else if (selectedSegment) selectSegment(null)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [pointCardOpen, selectedSegment, selectPoint, selectSegment])

  // The route is drawn UNDER the segments. SegmentLayer re-sorts its lines in
  // its own effects; this parent effect runs after them on every render and
  // puts the route back at the very bottom of the shared canvas.
  const routeCasingRef = useRef<L.Polyline | null>(null)
  const routeCoreRef = useRef<L.Polyline | null>(null)
  // The faint alternatives are clickable and mounted after the segments, so
  // they are pushed down too (just above the route) and segment clicks win.
  const altLinesRef = useRef(new Map<number, L.Polyline>())
  useEffect(() => {
    altLinesRef.current.forEach(line => line.bringToBack())
    routeCoreRef.current?.bringToBack()
    routeCasingRef.current?.bringToBack()
  })

  // Unified handler for map moves
  const handleMapMove = React.useCallback(
    (bbox: number[], center: [number, number], zoom: number) => {
      onMapMove(bbox, center, zoom)
    },
    [onMapMove],
  )

  return (
    <div style={{ height: '100vh', width: '100vw', position: 'relative' }}>
      <MapContainer
        center={viewport.center}
        zoom={viewport.zoom}
        preferCanvas={true}
        renderer={renderer}
        style={{ height: '100%', width: '100%', background: '#111' }}>
        {/* Keyed by style: the recolouring className is fixed when a layer is created. */}
        <TileLayer
          key={mapStyle}
          attribution={BASE_MAPS[mapStyle].attribution}
          url={BASE_MAPS[mapStyle].url}
          maxZoom={BASE_MAPS[mapStyle].maxZoom}
          className={BASE_MAPS[mapStyle].className}
        />
        <MapEvents onMove={handleMapMove} />
        <MapController viewport={viewport} />
        <MapClickHandler />

        <SegmentFocusController focus={segmentFocus} selected={selectedSegment} />

        {/* Route. With road segments on screen it is a blue "tube" with a dark
            core: the coloured segments sit in the core, and a stretch without
            quality data stays visibly blue-and-dark. */}
        {/* Other alternatives: faint, tap one to select it. */}
        {routeAlternatives
          ?.filter(r => r.index !== selectedRouteIndex)
          .map(r => (
            <Polyline
              key={`alt-${r.index}`}
              ref={line => {
                if (line) altLinesRef.current.set(r.index, line)
                else altLinesRef.current.delete(r.index)
              }}
              positions={r.points}
              eventHandlers={{ click: () => selectRouteAlternative(r.index) }}
              pathOptions={{ color: '#94a3b8', weight: 6, opacity: 0.35, lineCap: 'round' }}
            />
          ))}

        {routePoints && layers.segments && (
          <>
            <Polyline
              ref={routeCasingRef}
              positions={routePoints}
              interactive={false}
              pathOptions={{
                color: '#3b82f6', // blue-500
                weight: segmentWeight(viewport.zoom) + 8,
                opacity: 0.9,
                lineCap: 'round',
              }}
            />
            <Polyline
              ref={routeCoreRef}
              positions={routePoints}
              interactive={false}
              pathOptions={{
                color: '#0b1220',
                weight: segmentWeight(viewport.zoom) + 2,
                opacity: 1,
                lineCap: 'round',
              }}
            />
          </>
        )}
        {routePoints && !layers.segments && (
          <Polyline
            positions={routePoints}
            interactive={false}
            pathOptions={{
              color: '#3b82f6', // blue-500
              weight: 6,
              opacity: 0.6,
              lineCap: 'round',
            }}
          />
        )}

        {/* Zoomed-out overview: road-quality grid (colour = average RQI). */}
        {layers.grid && grid && grid.cells.length > 0 && <QualityGridLayer grid={grid} />}

        {/* Roads as coloured segments (colour = quality, strength = confidence). */}
        {layers.segments && (
          <SegmentLayer
            segments={segments}
            zoom={viewport.zoom}
            selected={selectedSegment}
            dimStale={dimStale}
            interactive={!pickingLocationFor}
            onSelect={selectSegment}
          />
        )}

        {/* Frame dots: the whole viewport at street level, otherwise only the
            frames of the selected segment. */}
        {dots.map((point) => {
          const { score } = resolveRqi(point, displaySource)
          const faded = dimStale && isStaleCapture(point.capture_date)

          return (
          <CircleMarker
            key={point.id}
            center={[point.latitude, point.longitude]}
            radius={layers.segments ? 5 : 6}
            pathOptions={{
              // On top of a same-coloured road line a dot needs a dark rim.
              color: layers.segments ? '#0b1220' : getRQIColor(score),
              fillColor: getRQIColor(score),
              fillOpacity: faded ? 0.12 : layers.segments ? 0.95 : 0.7,
              opacity: faded ? 0.25 : 1,
              weight: layers.segments ? 1.5 : 1
            }}
            eventHandlers={{
              click: () => {
                  if (!pickingLocationFor) {
                      selectPoint(point.id)
                  }
              },
            }}
          />
        )})}
      </MapContainer>

      <RoutePlanner />

      <MapStyleSwitcher currentStyle={mapStyle} onChange={setMapStyle} />

      {/* Capture dates exist for frame dots and road segments (not the grid). */}
      {(dots.length > 0 || (layers.segments && segments.length > 0)) && (
        <StaleImageToggle enabled={dimStale} onChange={setDimStale} />
      )}

      {/* Segment detail. A frame's own card (below) can open next to it; on a
          phone the segment sheet steps aside until that card is closed. */}
      {selectedSegment && (
        <SegmentDetailCard
          segment={selectedSegment}
          onClose={() => selectSegment(null)}
          behind={pointCardOpen}
        />
      )}

      {/* Frame detail. Keyed on the loaded detail (not on the viewport list):
          a frame of the selected segment is not part of that list. */}
      {pointCardOpen && (
        <PointDetailCard
          detail={selectedPointDetail!}
          loading={loadingDetail}
          onClose={() => selectPoint(null)}
          onTrain={onTrain}
        />
      )}

      {/* Nothing to draw here: say so instead of showing a bare map. */}
      {layers.segments && !loading && !segmentsLoading && (segmentsError || segmentsEmpty) && (
        <div className="map-notice" role="status">
          {segmentsError
            ? 'Az útszakaszok betöltése nem sikerült.'
            : 'Ezen a területen még nincs felmért út.'}
        </div>
      )}

      {/* Loading Overlay */}
      {(loading || (layers.segments && segmentsLoading)) && (
        <div
          style={{
            position: 'absolute',
            top: 20,
            left: '50%',
            transform: 'translateX(-50%)',
            background: 'rgba(0,0,0,0.7)',
            color: 'white',
            padding: '10px 20px',
            borderRadius: '20px',
            zIndex: 9999,
            backdropFilter: 'blur(10px)',
          }}>
          Útadatok betöltése…
        </div>
      )}
    </div>
  )
}

export default MapView
