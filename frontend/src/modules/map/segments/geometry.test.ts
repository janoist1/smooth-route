import { describe, it, expect } from 'vitest'
import {
  bearingDeg,
  distanceToPathM,
  haversineM,
  pathBbox,
  pathBounds,
  pathLengthM,
  pathMidpoint,
  streetViewUrl,
} from './geometry'
import type { LatLng } from './types'

// Budapest-ish coordinates; 0.001° of latitude is ~111 m.
const A: LatLng = [47.5, 19.04]
const B: LatLng = [47.501, 19.04]
const C: LatLng = [47.501, 19.042]

describe('distances', () => {
  it('measures a north-south step of 0.001° as ~111 m', () => {
    expect(haversineM(A, B)).toBeGreaterThan(110)
    expect(haversineM(A, B)).toBeLessThan(112.5)
    expect(haversineM(A, A)).toBe(0)
  })

  it('sums the legs of a path', () => {
    expect(pathLengthM([A, B, C])).toBeCloseTo(haversineM(A, B) + haversineM(B, C), 6)
    expect(pathLengthM([A])).toBe(0)
    expect(pathLengthM([])).toBe(0)
  })

  it('gives compass bearings', () => {
    expect(bearingDeg(A, B)).toBeCloseTo(0, 3) // north
    expect(bearingDeg(B, A)).toBeCloseTo(180, 3) // south
    expect(bearingDeg(B, C)).toBeGreaterThan(89) // east
    expect(bearingDeg(B, C)).toBeLessThan(91)
  })
})

describe('pathMidpoint', () => {
  it('is half-way along a straight segment, heading along it', () => {
    const mid = pathMidpoint([A, B])!
    expect(mid.lat).toBeCloseTo(47.5005, 6)
    expect(mid.lng).toBeCloseTo(19.04, 6)
    expect(mid.heading).toBeCloseTo(0, 3)
  })

  it('follows the path, not the straight line between the ends', () => {
    // A→B is ~111 m, B→C ~150 m: the half-way point lies on the second leg.
    const mid = pathMidpoint([A, B, C])!
    expect(mid.lat).toBeCloseTo(47.501, 6)
    expect(mid.lng).toBeGreaterThan(19.04)
    expect(mid.lng).toBeLessThan(19.042)
    expect(mid.heading).toBeGreaterThan(89)
    expect(mid.heading).toBeLessThan(91)
  })

  it('handles degenerate paths', () => {
    expect(pathMidpoint([])).toBeNull()
    expect(pathMidpoint([A])).toEqual({ lat: 47.5, lng: 19.04, heading: 0 })
    expect(pathMidpoint([A, A])).toEqual({ lat: 47.5, lng: 19.04, heading: 0 })
  })
})

describe('bounds', () => {
  it('returns south-west and north-east corners', () => {
    expect(pathBounds([B, A, C])).toEqual([
      [47.5, 19.04],
      [47.501, 19.042],
    ])
    expect(pathBounds([])).toBeNull()
  })

  it('builds a padded API bbox in [minLng, minLat, maxLng, maxLat] order', () => {
    expect(pathBbox([A, C])).toEqual([19.04, 47.5, 19.042, 47.501])
    const [minLng, minLat, maxLng, maxLat] = pathBbox([A, C], 30)!
    expect(minLat).toBeLessThan(47.5)
    expect(maxLat).toBeGreaterThan(47.501)
    expect(minLng).toBeLessThan(19.04)
    expect(maxLng).toBeGreaterThan(19.042)
    // 30 m is ~0.00027° of latitude.
    expect(47.5 - minLat).toBeCloseTo(0.00027, 4)
    expect(pathBbox([])).toBeNull()
  })
})

describe('distanceToPathM', () => {
  it('is ~0 on the path and grows sideways', () => {
    expect(distanceToPathM([47.5005, 19.04], [A, B])).toBeLessThan(0.5)
    // 0.0002° of longitude at this latitude is ~15 m.
    const d = distanceToPathM([47.5005, 19.0402], [A, B])
    expect(d).toBeGreaterThan(13)
    expect(d).toBeLessThan(17)
  })

  it('measures to the nearest end beyond the path', () => {
    const d = distanceToPathM([47.502, 19.04], [A, B])
    expect(d).toBeGreaterThan(110)
    expect(d).toBeLessThan(112.5)
  })

  it('handles single-point and empty paths', () => {
    expect(distanceToPathM(B, [A])).toBeGreaterThan(110)
    expect(distanceToPathM(A, [])).toBe(Infinity)
  })
})

describe('streetViewUrl', () => {
  it('builds the same free deep link the backend uses for points', () => {
    expect(streetViewUrl(47.50051234, 19.04, 92.6)).toBe(
      'https://www.google.com/maps/@?api=1&map_action=pano&viewpoint=47.500512,19.040000&heading=93&pitch=0',
    )
  })
})
