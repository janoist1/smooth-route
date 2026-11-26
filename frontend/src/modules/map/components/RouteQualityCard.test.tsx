import { describe, it, expect, vi, afterEach } from 'vitest'
import { cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import { fromSeverity as sv, rqiLevel, rqiValue } from '../../ui'
import RouteQualityCard from './RouteQualityCard'
import { formatScore } from '../segments/labels'
import type { RoadSegment, RouteQuality } from '../segments/types'

const segment = (id: string, over: Partial<RoadSegment> = {}): RoadSegment => ({
  id,
  path: [
    [47.5, 19.04],
    [47.501, 19.04],
  ],
  // RQI values as sv(severity), 1 = best: valid for either scale numbering.
  rqi: sv(4),
  score: sv(3.8),
  pBad: 0.9,
  confidence: 0.8,
  confidenceLevel: 'high',
  nImages: 12,
  lengthM: 320,
  roadName: 'Kossuth Lajos utca',
  highway: 'residential',
  captureDateMin: '2023-05',
  captureDateMax: '2025-08',
  ...over,
})

const quality = (over: Partial<RouteQuality> = {}): RouteQuality => ({
  totalLengthM: 62380,
  coveredLengthM: 30000,
  lengthByRqi: [15000, 9000, 4500, 1500],
  meanScore: sv(1.9),
  worstSegments: [
    segment('w1'),
    segment('w2', { roadName: null, highway: 'tertiary', rqi: sv(3), lengthM: 1240 }),
  ],
  ...over,
})

const renderCard = (
  props: Partial<React.ComponentProps<typeof RouteQualityCard>> = {},
) =>
  render(
    <RouteQualityCard
      quality={quality()}
      loading={false}
      error={null}
      onSelectSegment={() => {}}
      {...props}
    />,
  )

describe('RouteQualityCard', () => {
  afterEach(cleanup)

  it('shows the total length and the measured share', () => {
    renderCard()
    expect(screen.getByTestId('route-total')).toHaveTextContent('62,4 km')
    expect(screen.getByTestId('route-coverage')).toHaveTextContent('48%')
    expect(screen.getByTestId('route-coverage')).toHaveTextContent('felmérve (30,0 km)')
  })

  it('draws the stacked bar with one part per class, sized by share of the route', () => {
    renderCard()
    // 15000 / 62380 = 24.05 %
    expect(screen.getByTestId('route-bar-excellent')).toHaveStyle({ width: '24.05%' })
    expect(screen.getByTestId('route-bar-good')).toHaveStyle({ width: '14.43%' })
    expect(screen.getByTestId('route-bar-fair')).toHaveStyle({ width: '7.21%' })
    expect(screen.getByTestId('route-bar-poor')).toHaveStyle({ width: '2.40%' })
    expect(screen.getByRole('img')).toHaveAccessibleName(
      'Kiváló: 15,0 km, Jó: 9,0 km, Közepes: 4,5 km, Rossz: 1,5 km, nincs adat: 52%',
    )
  })

  it('lists the length per class and the unmeasured rest', () => {
    renderCard()
    expect(screen.getByTestId('route-class-excellent')).toHaveTextContent('Kiváló 15,0 km')
    expect(screen.getByTestId('route-class-poor')).toHaveTextContent('Rossz 1,5 km')
    expect(screen.getByTestId('route-class-unknown')).toHaveTextContent('nincs adat 52%')
  })

  it('leaves out classes with no length', () => {
    renderCard({ quality: quality({ coveredLengthM: 24000, lengthByRqi: [15000, 9000, 0, 0] }) })
    expect(screen.queryByTestId('route-bar-fair')).not.toBeInTheDocument()
    expect(screen.queryByTestId('route-class-poor')).not.toBeInTheDocument()
  })

  it('shows the length-weighted average as a label', () => {
    renderCard()
    expect(screen.getByTestId('route-mean')).toHaveTextContent(
      `Átlagos minőség: Jó (${formatScore(sv(1.9))}, hosszal súlyozva)`,
    )
  })

  it('colours the average badge like its label (Jó + 0,4 is still "Jó")', () => {
    renderCard({ quality: quality({ meanScore: sv(2.4) }) })
    const badge = screen.getByTestId('route-mean-badge')
    expect(badge).toHaveTextContent('Jó')
    expect(badge.style.getPropertyValue('--road-color')).toBe(rqiLevel(rqiValue('good'))!.color)
  })

  it('lists the worst segments and reports a click', () => {
    const onSelectSegment = vi.fn()
    renderCard({ onSelectSegment })
    expect(screen.getByText('Legrosszabb szakaszok')).toBeInTheDocument()

    const buttons = screen.getAllByRole('button')
    expect(buttons).toHaveLength(2)
    expect(buttons[0]).toHaveTextContent('Kossuth Lajos utca')
    expect(buttons[0]).toHaveTextContent('320 m')
    expect(buttons[0]).toHaveTextContent('Rossz')
    expect(buttons[1]).toHaveTextContent('Gyűjtőút (névtelen)')
    expect(buttons[1]).toHaveTextContent('1,2 km')

    fireEvent.click(buttons[1])
    expect(onSelectSegment).toHaveBeenCalledTimes(1)
    expect(onSelectSegment.mock.calls[0][0].id).toBe('w2')
  })

  it('caps the worst-segment list at five', () => {
    const many = Array.from({ length: 8 }, (_, i) => segment(`w${i}`))
    renderCard({ quality: quality({ worstSegments: many }) })
    expect(screen.getAllByRole('button')).toHaveLength(5)
  })

  it('says clearly when there is no data for the route', () => {
    renderCard({
      quality: quality({
        coveredLengthM: 0,
        lengthByRqi: [0, 0, 0, 0],
        meanScore: null,
        worstSegments: [],
      }),
    })
    expect(screen.getByTestId('route-total')).toHaveTextContent('62,4 km')
    expect(screen.getByTestId('route-coverage')).toHaveTextContent('0%')
    expect(screen.getByRole('status')).toHaveTextContent('Nincs adat erre az útvonalra.')
    expect(screen.queryByRole('img')).not.toBeInTheDocument()
    expect(screen.queryByTestId('route-mean')).not.toBeInTheDocument()
    expect(screen.queryByText('Legrosszabb szakaszok')).not.toBeInTheDocument()
  })

  it('warns when only a small part of the route is measured', () => {
    renderCard({ quality: quality({ coveredLengthM: 6000, lengthByRqi: [6000, 0, 0, 0] }) })
    expect(screen.getByRole('note')).toHaveTextContent('csak kis része felmért')
  })

  it('does not warn at normal coverage', () => {
    renderCard()
    expect(screen.queryByRole('note')).not.toBeInTheDocument()
  })

  it('shows a loading state', () => {
    renderCard({ quality: null, loading: true })
    const card = screen.getByRole('region', { name: 'Útvonal minősége' })
    expect(card).toHaveAttribute('aria-busy', 'true')
    expect(within(card).getByText('Útminőség számítása…')).toBeInTheDocument()
  })

  it('shows an error state', () => {
    renderCard({ quality: null, error: 'boom' })
    expect(screen.getByRole('alert')).toHaveTextContent('Az útvonal minősége most nem érhető el.')
  })

  it('renders nothing without a result (e.g. backend without the API)', () => {
    const { container } = renderCard({ quality: null })
    expect(container).toBeEmptyDOMElement()
  })
})
