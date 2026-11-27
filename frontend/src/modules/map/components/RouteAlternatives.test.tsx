import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import RouteAlternatives from './RouteAlternatives'
import type { RouteAlternative } from '../alternatives'

const quality = { totalLengthM: 1000, coveredLengthM: 900, lengthByRqi: [900, 0, 0, 0], meanScore: null, worstSegments: [] }
const route = (index: number, extra: Partial<RouteAlternative>): RouteAlternative => ({
  index,
  points: [[47.5, 19], [47.49, 19.05]],
  distanceM: 12400,
  durationS: 1380,
  summary: `M${index}`,
  quality,
  coverage: 0.9,
  isFastest: false,
  isSmoothest: false,
  smoothestConfident: false,
  ...extra,
})

describe('RouteAlternatives', () => {
  afterEach(cleanup)

  it('shows badges, time, coverage and selects on tap', () => {
    const onSelect = vi.fn()
    render(
      <RouteAlternatives
        routes={[route(0, { isFastest: true }), route(1, { isSmoothest: true, smoothestConfident: true, durationS: 1560 })]}
        selectedIndex={1}
        onSelect={onSelect}
      />,
    )
    expect(screen.getByText('Leggyorsabb')).toBeInTheDocument()
    expect(screen.getByText('Legsimább')).toBeInTheDocument()
    expect(screen.getByText('Legsimább')).toHaveStyle({ background: '#16a34a' })
    expect(screen.getByText('Legsimább')).not.toHaveAttribute('title')
    expect(screen.queryByText('Legsimább?')).not.toBeInTheDocument()
    expect(screen.getByText(/\+3 perc/)).toBeInTheDocument()
    expect(screen.getByTestId('route-alt-1')).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getAllByText(/90\s*% felmérve/)).toHaveLength(2)
    fireEvent.click(screen.getByTestId('route-alt-0'))
    expect(onSelect).toHaveBeenCalledWith(0)
  })

  it('shows a muted uncertain badge with rounded coverage in the Hungarian tooltip', () => {
    render(
      <RouteAlternatives
        routes={[route(0, { isFastest: true }), route(1, { isSmoothest: true, coverage: 0.234 })]}
        selectedIndex={1}
        onSelect={() => {}}
      />,
    )
    expect(screen.getByText('Legsimább?')).toHaveStyle({ background: '#64748b' })
    expect(screen.getByText('Legsimább?')).toHaveAttribute('title', 'Kevés adat: az útvonal 23%-áról van mérés')
    expect(screen.queryByText('Legsimább')).not.toBeInTheDocument()
    expect(screen.getByText(/23\s*% felmérve/)).toBeInTheDocument()
  })

  it('renders nothing for a single route', () => {
    const { container } = render(
      <RouteAlternatives routes={[route(0, { isFastest: true })]} selectedIndex={0} onSelect={() => {}} />,
    )
    expect(container).toBeEmptyDOMElement()
  })
})
