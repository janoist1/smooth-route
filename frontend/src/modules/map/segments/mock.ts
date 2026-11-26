// Deterministic mock data for the segment API — ONLY for visual checks while
// the backend is not there yet (see segmentMocksEnabled in ./api.ts). Loaded
// with a dynamic import, so it never ends up in the main production chunk.
import { haversineM, pathLengthM } from './geometry'
import { SEGMENT_MIN_ZOOM } from './style'
import type { LatLng, RoadSegment, RouteQuality } from './types'

// A jittered street lattice: nodes every ~330 m; each lattice edge is one segment.
const STEP_LAT = 0.003
const STEP_LNG = 0.0045
const MAX_NODES_PER_AXIS = 70

// Small integer hash → [0, 1). Stable across pans, so segments don't flicker.
const rand = (a: number, b: number, salt: number): number => {
  let h = (a * 374761393 + b * 668265263 + salt * 2147483647) | 0
  h = Math.imul(h ^ (h >>> 13), 1274126177)
  h ^= h >>> 16
  return (h >>> 0) / 4294967296
}

const node = (i: number, j: number): LatLng => [
  i * STEP_LAT + (rand(i, j, 1) - 0.5) * STEP_LAT * 0.35,
  j * STEP_LNG + (rand(i, j, 2) - 0.5) * STEP_LNG * 0.35,
]

const STREETS = ['Váci út', 'Kossuth Lajos utca', 'Petőfi Sándor utca', 'Rákóczi út', 'Fő utca', 'Bartók Béla út']
const HIGHWAYS = ['residential', 'residential', 'tertiary', 'secondary', 'primary', 'service']

const month = (year: number, r: number) => `${year}-${String(1 + Math.floor(r * 12)).padStart(2, '0')}`

const makeSegment = (id: string, path: LatLng[], i: number, j: number, salt: number): RoadSegment => {
  const quality = rand(i, j, salt + 10)
  const rqi = quality < 0.38 ? 1 : quality < 0.68 ? 2 : quality < 0.88 ? 3 : 4
  const confidence = Math.round((0.15 + 0.85 * rand(i, j, salt + 20)) * 100) / 100
  const confidenceLevel = confidence >= 0.7 ? 'high' : confidence >= 0.4 ? 'medium' : 'low'
  const lengthM = pathLengthM(path)
  const named = rand(i, j, salt + 30) > 0.15
  const oldest = 2012 + Math.floor(rand(i, j, salt + 40) * 12)
  // Always a later year than the oldest, so min <= max whatever the months are.
  const newest = Math.min(2025, oldest + 1 + Math.floor(rand(i, j, salt + 50) * 3))
  return {
    id,
    path,
    rqi,
    score: Math.round((rqi + (rand(i, j, salt + 60) - 0.5) * 0.9) * 100) / 100,
    pBad: Math.round(Math.max(0.01, Math.min(0.99, (rqi - 1) / 3 + (rand(i, j, salt + 70) - 0.5) * 0.3)) * 100) / 100,
    confidence,
    confidenceLevel,
    nImages: Math.max(1, Math.round((lengthM / 15) * (0.2 + confidence))),
    lengthM: Math.round(lengthM),
    roadName: named ? STREETS[Math.floor(rand(i, j, salt + 80) * STREETS.length)] : null,
    highway: HIGHWAYS[Math.floor(rand(i, j, salt + 90) * HIGHWAYS.length)],
    captureDateMin: month(oldest, rand(i, j, salt + 100)),
    captureDateMax: month(newest, rand(i, j, salt + 110)),
  }
}

/** bbox = [minLng, minLat, maxLng, maxLat]; [] below the segment zoom, like the API. */
export const mockRoadSegments = (bbox: number[], zoom: number): RoadSegment[] => {
  if (zoom < SEGMENT_MIN_ZOOM || bbox.length < 4) return []
  const [minLng, minLat, maxLng, maxLat] = bbox
  const i0 = Math.floor(minLat / STEP_LAT)
  const j0 = Math.floor(minLng / STEP_LNG)
  const i1 = Math.min(Math.ceil(maxLat / STEP_LAT), i0 + MAX_NODES_PER_AXIS)
  const j1 = Math.min(Math.ceil(maxLng / STEP_LNG), j0 + MAX_NODES_PER_AXIS)

  const segments: RoadSegment[] = []
  for (let i = i0; i <= i1; i++) {
    for (let j = j0; j <= j1; j++) {
      // ~12% of the edges are missing: real coverage has holes.
      if (rand(i, j, 3) > 0.12) segments.push(makeSegment(`mock-e-${i}-${j}`, [node(i, j), node(i, j + 1)], i, j, 0))
      if (rand(i, j, 4) > 0.12) segments.push(makeSegment(`mock-n-${i}-${j}`, [node(i, j), node(i + 1, j)], i, j, 500))
    }
  }
  return segments
}

/** Route cut into ~400 m pieces; ~70% of them "measured". `?mockCoverage=0` → no data. */
export const mockRouteQuality = (path: LatLng[]): RouteQuality => {
  const totalLengthM = pathLengthM(path)
  const noData =
    typeof window !== 'undefined' &&
    new URLSearchParams(window.location.search).get('mockCoverage') === '0'

  const pieces: LatLng[][] = []
  let current: LatLng[] = path.length ? [path[0]] : []
  let acc = 0
  for (let k = 1; k < path.length; k++) {
    acc += haversineM(path[k - 1], path[k])
    current.push(path[k])
    if (acc >= 400) {
      pieces.push(current)
      current = [path[k]]
      acc = 0
    }
  }
  if (current.length > 1) pieces.push(current)

  const lengthByRqi = [0, 0, 0, 0]
  const measured: RoadSegment[] = []
  let scoreLength = 0
  pieces.forEach((piece, k) => {
    if (noData || rand(k, 7, 5) > 0.7) return
    const segment = makeSegment(`mock-route-${k}`, piece, k, 7, 900)
    measured.push(segment)
    lengthByRqi[(segment.rqi ?? 1) - 1] += segment.lengthM
    scoreLength += (segment.score ?? 0) * segment.lengthM
  })
  const coveredLengthM = lengthByRqi.reduce((sum, metres) => sum + metres, 0)

  return {
    totalLengthM,
    coveredLengthM: Math.min(totalLengthM, coveredLengthM),
    lengthByRqi,
    meanScore: coveredLengthM > 0 ? scoreLength / coveredLengthM : null,
    worstSegments: [...measured].sort((a, b) => (b.score ?? 0) - (a.score ?? 0)).slice(0, 5),
  }
}
