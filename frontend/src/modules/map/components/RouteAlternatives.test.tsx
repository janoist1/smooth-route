import { describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
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
  ...extra,
})

describe('RouteAlternatives', () => {
  it('shows badges, time, coverage and selects on tap', () => {
    const onSelect = vi.fn()
    render(
      <RouteAlternatives
        routes={[route(0, { isFastest: true }), route(1, { isSmoothest: true, durationS: 1560, coverage: 0.2 })]}
        selectedIndex={1}
        onSelect={onSelect}
      />,
    )
    expect(screen.getByText('Leggyorsabb')).toBeInTheDocument()
    expect(screen.getByText('Legsimább')).toBeInTheDocument()
    expect(screen.getByText(/\+3 perc/)).toBeInTheDocument()
    expect(screen.getByTestId('route-alt-1')).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByText(/20\s*% felmérve/)).toBeInTheDocument()
    fireEvent.click(screen.getByTestId('route-alt-0'))
    expect(onSelect).toHaveBeenCalledWith(0)
  })

  it('renders nothing for a single route', () => {
    const { container } = render(
      <RouteAlternatives routes={[route(0, { isFastest: true })]} selectedIndex={0} onSelect={() => {}} />,
    )
    expect(container).toBeEmptyDOMElement()
  })
})
