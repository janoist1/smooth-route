import { describe, it, expect } from 'vitest'
import { GRID_MAX_ZOOM, shouldShowGrid, GRID_FILL_OPACITY } from './aggregation'

describe('shouldShowGrid', () => {
  it('shows the quality grid below the threshold, raw points at/above it', () => {
    expect(shouldShowGrid(GRID_MAX_ZOOM - 1)).toBe(true)
    expect(shouldShowGrid(GRID_MAX_ZOOM)).toBe(false)
    expect(shouldShowGrid(GRID_MAX_ZOOM + 2)).toBe(false)
    expect(shouldShowGrid(6)).toBe(true)
  })
})

describe('GRID_FILL_OPACITY', () => {
  it('is translucent so the base map shows through', () => {
    expect(GRID_FILL_OPACITY).toBeGreaterThan(0)
    expect(GRID_FILL_OPACITY).toBeLessThan(1)
  })
})
