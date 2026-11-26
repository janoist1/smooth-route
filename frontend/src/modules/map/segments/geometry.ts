// Pure geometry helpers for road segments (no Leaflet import — unit-testable).
import type { Bounds, LatLng } from './types'

const EARTH_RADIUS_M = 6371008.8
const toRad = (deg: number) => (deg * Math.PI) / 180
const toDeg = (rad: number) => (rad * 180) / Math.PI

/** Great-circle distance in metres. */
export const haversineM = (a: LatLng, b: LatLng): number => {
  const dLat = toRad(b[0] - a[0])
  const dLng = toRad(b[1] - a[1])
  const h =
    Math.sin(dLat / 2) ** 2 + Math.cos(toRad(a[0])) * Math.cos(toRad(b[0])) * Math.sin(dLng / 2) ** 2
  return 2 * EARTH_RADIUS_M * Math.asin(Math.min(1, Math.sqrt(h)))
}

export const pathLengthM = (path: LatLng[]): number => {
  let total = 0
  for (let i = 1; i < path.length; i++) total += haversineM(path[i - 1], path[i])
  return total
}

/** Compass bearing a → b in degrees, 0–360 (0 = north, 90 = east). */
export const bearingDeg = (a: LatLng, b: LatLng): number => {
  const lat1 = toRad(a[0])
  const lat2 = toRad(b[0])
  const dLng = toRad(b[1] - a[1])
  const y = Math.sin(dLng) * Math.cos(lat2)
  const x = Math.cos(lat1) * Math.sin(lat2) - Math.sin(lat1) * Math.cos(lat2) * Math.cos(dLng)
  return (toDeg(Math.atan2(y, x)) + 360) % 360
}

export interface PathMidpoint {
  lat: number
  lng: number
  /** Direction of travel at the midpoint (degrees) — points Street View along the road. */
  heading: number
}

/** The point half-way ALONG the path (not the bbox centre, which can be off-road). */
export const pathMidpoint = (path: LatLng[]): PathMidpoint | null => {
  if (path.length === 0) return null
  if (path.length === 1) return { lat: path[0][0], lng: path[0][1], heading: 0 }

  const half = pathLengthM(path) / 2
  let walked = 0
  for (let i = 1; i < path.length; i++) {
    const a = path[i - 1]
    const b = path[i]
    const leg = haversineM(a, b)
    if (walked + leg >= half && leg > 0) {
      const t = (half - walked) / leg
      return {
        lat: a[0] + (b[0] - a[0]) * t,
        lng: a[1] + (b[1] - a[1]) * t,
        heading: bearingDeg(a, b),
      }
    }
    walked += leg
  }
  // Degenerate path (all points identical).
  const last = path[path.length - 1]
  return { lat: last[0], lng: last[1], heading: 0 }
}

/** [[south, west], [north, east]] of the path; null for an empty path. */
export const pathBounds = (path: LatLng[]): Bounds | null => {
  if (path.length === 0) return null
  let minLat = Infinity
  let minLng = Infinity
  let maxLat = -Infinity
  let maxLng = -Infinity
  for (const [lat, lng] of path) {
    if (lat < minLat) minLat = lat
    if (lat > maxLat) maxLat = lat
    if (lng < minLng) minLng = lng
    if (lng > maxLng) maxLng = lng
  }
  return [
    [minLat, minLng],
    [maxLat, maxLng],
  ]
}

const M_PER_DEG_LAT = 111320

/** API bbox [minLng, minLat, maxLng, maxLat] around the path, padded by `padM` metres. */
export const pathBbox = (path: LatLng[], padM = 0): number[] | null => {
  const bounds = pathBounds(path)
  if (!bounds) return null
  const [[minLat, minLng], [maxLat, maxLng]] = bounds
  const midLat = (minLat + maxLat) / 2
  const padLat = padM / M_PER_DEG_LAT
  const padLng = padM / (M_PER_DEG_LAT * Math.max(0.01, Math.cos(toRad(midLat))))
  return [minLng - padLng, minLat - padLat, maxLng + padLng, maxLat + padLat]
}

/** Shortest distance (metres) from a point to a polyline; Infinity for an empty path. */
export const distanceToPathM = (point: LatLng, path: LatLng[]): number => {
  if (path.length === 0) return Infinity
  // Local equirectangular projection around the point: accurate to well under
  // a metre at the tens-of-metres distances this is used for.
  const kLat = M_PER_DEG_LAT
  const kLng = M_PER_DEG_LAT * Math.cos(toRad(point[0]))
  const xy = (p: LatLng): [number, number] => [(p[1] - point[1]) * kLng, (p[0] - point[0]) * kLat]

  if (path.length === 1) return Math.hypot(...xy(path[0]))

  let best = Infinity
  for (let i = 1; i < path.length; i++) {
    const [ax, ay] = xy(path[i - 1])
    const [bx, by] = xy(path[i])
    const dx = bx - ax
    const dy = by - ay
    const len2 = dx * dx + dy * dy
    // Closest point on the leg to the origin (= the query point).
    const t = len2 === 0 ? 0 : Math.max(0, Math.min(1, -(ax * dx + ay * dy) / len2))
    const d = Math.hypot(ax + dx * t, ay + dy * t)
    if (d < best) best = d
  }
  return best
}

/**
 * Free Google Maps Street View deep link (no API call). Same URL scheme the
 * backend builds for `Point.streetViewUrl` (backend/app/graphql/types.py) —
 * Google resolves the nearest panorama to the viewpoint.
 */
export const streetViewUrl = (lat: number, lng: number, heading = 0): string =>
  'https://www.google.com/maps/@?api=1&map_action=pano' +
  `&viewpoint=${lat.toFixed(6)},${lng.toFixed(6)}&heading=${Math.round(heading)}&pitch=0`
