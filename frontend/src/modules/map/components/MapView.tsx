import React, { useEffect, useState, useMemo } from 'react'
import { MapContainer, TileLayer, Polyline, useMapEvents } from 'react-leaflet'
import 'leaflet/dist/leaflet.css'
import { useMap } from '../hooks'
import PointDetailCard from './PointDetailCard'
import MapStyleSwitcher from './MapStyleSwitcher'
import type { MapStyle } from './MapStyleSwitcher'

import { getRQIColor } from '../../ui/utils/colors'

const TILE_LAYERS: Record<MapStyle, { url: string; attribution: string }> = {
  dark: {
    url: 'https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png',
    attribution: '&copy; CARTO',
  },
  light: {
    url: 'https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png',
    attribution: '&copy; CARTO',
  },
  satellite: {
    url: 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
    attribution: '&copy; Esri',
  },
  street: {
    url: 'https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',
    attribution: '&copy; OSM',
  },
}

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

  // Initial initialization (if needed for fetch)
  useEffect(() => {
    const bounds = map.getBounds()
    const bbox = [bounds.getWest(), bounds.getSouth(), bounds.getEast(), bounds.getNorth()]
    const center = map.getCenter()
    onMove(bbox, [center.lat, center.lng], map.getZoom())
  }, [map, onMove])

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

interface MapViewProps {
  onTrain: (id: string | number) => void
  onMapMove: (bbox: number[], center: [number, number], zoom: number) => void
}

const MapView: React.FC<MapViewProps> = ({ onTrain, onMapMove }) => {
  const {
    points,
    loading,
    fetchPoints,
    selectPoint,
    selectedPointDetail,
    loadingDetail,
    selectedPoint,
    viewport,
  } = useMap()
  const [mapStyle, setMapStyle] = useState<MapStyle>('dark')

  // Unified handler for map moves
  const handleMapMove = React.useCallback(
    (bbox: number[], center: [number, number], zoom: number) => {
      fetchPoints(bbox)
      onMapMove(bbox, center, zoom)
    },
    [fetchPoints, onMapMove],
  )

  // Generate segments for traffic-like visualization
  const segments = useMemo(() => {
    const segs = []
    // Sort by ID to ensure order (assuming ID correlates with capture time/route)
    const sortedPoints = [...points].sort((a, b) => a.id - b.id)

    for (let i = 0; i < sortedPoints.length - 1; i++) {
      const p1 = sortedPoints[i]
      const p2 = sortedPoints[i + 1]

      // Simple distance check to avoid cross-map lines (0.01 deg ~= 1km)
      const dist = Math.sqrt(
        Math.pow(p1.latitude - p2.latitude, 2) + Math.pow(p1.longitude - p2.longitude, 2),
      )

      if (dist < 0.01) {
        // ~1km threshold to allow slightly sparser data connection
        segs.push({
          positions: [
            [p1.latitude, p1.longitude],
            [p2.latitude, p2.longitude],
          ] as [number, number][],
          color: getRQIColor(p1.rqi_score),
          point: p1, // Attach point data for click handler
        })
      }
    }
    return segs
  }, [points])

  return (
    <div style={{ height: '100vh', width: '100vw', position: 'relative' }}>
      <MapContainer
        center={viewport.center}
        zoom={viewport.zoom}
        style={{ height: '100%', width: '100%', background: '#111' }}>
        <TileLayer
          attribution={TILE_LAYERS[mapStyle].attribution}
          url={TILE_LAYERS[mapStyle].url}
        />
        <MapEvents onMove={handleMapMove} />
        <MapController viewport={viewport} />

        {/* Traffic Segments (Lines) */}
        {segments.map((seg, idx) => (
          <Polyline
            key={`seg-${idx}`}
            positions={seg.positions}
            pathOptions={{
              color: seg.color,
              weight: 8, // Slightly thicker for better visibility
              opacity: 0.9,
              lineCap: 'round',
            }}
            eventHandlers={{
              click: () => selectPoint(seg.point.id),
            }}
          />
        ))}
      </MapContainer>

      <MapStyleSwitcher currentStyle={mapStyle} onChange={setMapStyle} />

      {/* Detail Overlay */}
      {(selectedPoint || loadingDetail) && (
        <PointDetailCard
          detail={selectedPointDetail!}
          loading={loadingDetail}
          onClose={() => selectPoint(null)}
          onTrain={onTrain}
        />
      )}

      {/* Loading Overlay */}
      {loading && (
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
          Loading Road Data...
        </div>
      )}
    </div>
  )
}

export default MapView
