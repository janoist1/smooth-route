import React, { useEffect, useState } from 'react'
import { MapContainer, TileLayer, CircleMarker, Polyline, useMapEvents } from 'react-leaflet'
import 'leaflet/dist/leaflet.css'
import { useMap } from '../hooks'
import PointDetailCard from './PointDetailCard'
import MapStyleSwitcher from './MapStyleSwitcher'
import RoutePlanner from './RoutePlanner'
import type { MapStyle } from './MapStyleSwitcher'

import { getRQIColor, resolveRqi } from '../../ui'
import { useRqiDisplaySource } from '../../settings'
import QualityGridLayer from './QualityGridLayer'

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
    selectedPoint,
    viewport,
    routePoints,
    pickingLocationFor,
  } = useMap()
  const [mapStyle, setMapStyle] = useState<MapStyle>('dark')

  const displaySource = useRqiDisplaySource()

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
        style={{ height: '100%', width: '100%', background: '#111' }}>
        <TileLayer
          attribution={TILE_LAYERS[mapStyle].attribution}
          url={TILE_LAYERS[mapStyle].url}
        />
        <MapEvents onMove={handleMapMove} />
        <MapController viewport={viewport} />
        <MapClickHandler />

        {/* Route Visualization */}
        {routePoints && (
          <Polyline
            positions={routePoints}
            pathOptions={{
              color: '#3b82f6', // blue-500
              weight: 6,
              opacity: 0.6,
              lineCap: 'round',
            }}
          />
        )}

        {/* Zoomed-out overview: road-quality grid (colour = average RQI). */}
        {grid && grid.cells.length > 0 && <QualityGridLayer grid={grid} />}

        {/* Data Points (Markers) */}
        {points.map((point) => {
          const { score } = resolveRqi(point, displaySource)

          return (
          <CircleMarker
            key={point.id}
            center={[point.latitude, point.longitude]}
            radius={6}
            pathOptions={{
              color: getRQIColor(score),
              fillColor: getRQIColor(score),
              fillOpacity: 0.7,
              weight: 1
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
