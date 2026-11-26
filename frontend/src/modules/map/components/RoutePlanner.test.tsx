import { describe, it, expect, vi, afterEach } from 'vitest'
import { cleanup, render, screen } from '@testing-library/react'
import RoutePlanner from './RoutePlanner'
import type { Viewer } from '../../auth'

let viewer: Viewer | null = null
vi.mock('../../auth', () => ({ useViewer: () => ({ viewer, isAdmin: viewer?.role === 'admin', loading: false }) }))

// A planned route is on the map; everything else idle.
vi.mock('../hooks', () => ({
  useMap: () => ({
    isPlanningRoute: false,
    isAnalyzingRoute: false,
    routeAnalysisJobId: null,
    error: null,
    routePoints: [
      [47.5, 19.0],
      [47.2, 18.4],
    ],
    origin: 'Budapest',
    destination: 'Székesfehérvár',
    pickingLocationFor: null,
    job: null,
    clearRoute: vi.fn(),
    cancelPickingLocation: vi.fn(),
    planRoute: vi.fn(),
    analyzeRoute: vi.fn(),
    setRouteForm: vi.fn(),
    startPickingLocation: vi.fn(),
  }),
}))

// Route-quality summary state (its own card has separate tests).
vi.mock('../segments/hooks', () => ({
  useRoadSegments: () => ({
    routeQuality: null,
    routeQualityLoading: false,
    routeQualityError: null,
    focusSegment: vi.fn(),
  }),
}))

describe('RoutePlanner analyze button', () => {
  afterEach(cleanup)

  it('is hidden for anonymous visitors (processRoute needs an admin)', () => {
    viewer = null
    render(<RoutePlanner />)
    expect(screen.getByRole('button', { name: /Útvonal Mutatása/ })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Elemzés Indítása/ })).not.toBeInTheDocument()
  })

  it('is hidden for a signed-in non-admin', () => {
    viewer = { clerkId: 'user_1', email: null, role: 'user' }
    render(<RoutePlanner />)
    expect(screen.queryByRole('button', { name: /Elemzés Indítása/ })).not.toBeInTheDocument()
  })

  it('is shown to an admin once a route is planned', () => {
    viewer = { clerkId: 'user_1', email: null, role: 'admin' }
    render(<RoutePlanner />)
    expect(screen.getByRole('button', { name: /Elemzés Indítása/ })).toBeInTheDocument()
  })
})
