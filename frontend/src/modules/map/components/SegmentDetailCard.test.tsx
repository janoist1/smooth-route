import { describe, it, expect, vi, beforeAll, afterAll, afterEach } from 'vitest'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import SegmentDetailCard from './SegmentDetailCard'
import type { RoadSegment } from '../segments/types'

const segment = (over: Partial<RoadSegment> = {}): RoadSegment => ({
  id: 'seg-1',
  path: [
    [47.5, 19.04],
    [47.501, 19.04],
  ],
  rqi: 2,
  score: 2.34,
  pBad: 0.127,
  confidence: 0.87,
  confidenceLevel: 'high',
  nImages: 24,
  lengthM: 430,
  roadName: 'Váci út',
  highway: 'primary',
  captureDateMin: '2023-05',
  captureDateMax: '2025-08',
  ...over,
})

const renderCard = (over: Partial<RoadSegment> = {}, onClose = () => {}) =>
  render(<SegmentDetailCard segment={segment(over)} onClose={onClose} />)

describe('SegmentDetailCard', () => {
  beforeAll(() => {
    vi.useFakeTimers({ toFake: ['Date'] })
    vi.setSystemTime(new Date(2026, 10, 18))
  })
  afterAll(() => vi.useRealTimers())
  afterEach(cleanup)

  it('shows the road name, type and length', () => {
    renderCard()
    expect(screen.getByRole('heading', { name: 'Váci út' })).toBeInTheDocument()
    expect(screen.getByTestId('segment-subtitle')).toHaveTextContent('főút · 430 m')
  })

  it('titles an unnamed road by its type (without repeating it)', () => {
    renderCard({ roadName: null, highway: 'residential', lengthM: 1240 })
    expect(screen.getByRole('heading', { name: 'Lakóutca (névtelen)' })).toBeInTheDocument()
    expect(screen.getByTestId('segment-subtitle')).toHaveTextContent(/^1,2 km$/)
  })

  it('shows the quality label, score and bad-road probability', () => {
    renderCard()
    expect(screen.getByTestId('segment-quality')).toHaveTextContent('Jó')
    expect(screen.getByTestId('segment-quality')).toHaveTextContent('Pontszám: 2,3 (1 = kiváló, 4 = rossz)')
    expect(screen.getByTestId('segment-pbad')).toHaveTextContent('Rossz út valószínűsége13%')
  })

  it('explains the confidence in plain words', () => {
    renderCard()
    const block = screen.getByTestId('segment-confidence')
    expect(block).toHaveTextContent('Megbízhatóság: magas (87%)')
    expect(block).toHaveTextContent('24 képkocka alapján; a képek egybehangzóan ugyanazt mutatják.')
  })

  it('warns about a low-confidence estimate', () => {
    renderCard({ confidence: 0.2, confidenceLevel: 'low', nImages: 2 })
    const block = screen.getByTestId('segment-confidence')
    expect(block).toHaveTextContent('Megbízhatóság: alacsony (20%)')
    expect(block).toHaveTextContent('2 képkocka alapján; kevés a kép, vagy a becslések ellentmondanak')
  })

  it('shows the capture range without a warning for recent images', () => {
    renderCard()
    expect(screen.getByTestId('segment-capture')).toHaveTextContent('Képek készültek: 2023-05 – 2025-08')
    expect(screen.queryByRole('note')).not.toBeInTheDocument()
    expect(screen.queryByTestId('segment-partly-stale')).not.toBeInTheDocument()
  })

  it('warns when even the newest image is older than 4 years', () => {
    renderCard({ captureDateMin: '2012-07', captureDateMax: '2019-06' })
    expect(screen.getByTestId('segment-capture')).toHaveTextContent('2012-07 – 2019-06')
    expect(screen.getByRole('note')).toHaveTextContent('4 évnél régebbi képek')
  })

  it('only hints when part of the images is old', () => {
    renderCard({ captureDateMin: '2019-06', captureDateMax: '2025-08' })
    expect(screen.queryByRole('note')).not.toBeInTheDocument()
    expect(screen.getByTestId('segment-partly-stale')).toHaveTextContent(
      'A képek egy része 4 évnél régebbi.',
    )
  })

  it('says unknown (and does not warn) without capture dates', () => {
    renderCard({ captureDateMin: null, captureDateMax: null })
    expect(screen.getByTestId('segment-capture')).toHaveTextContent('Képek készültek: ismeretlen')
    expect(screen.queryByRole('note')).not.toBeInTheDocument()
  })

  it('links to Street View at the middle of the segment, looking along it', () => {
    renderCard()
    const link = screen.getByRole('link', { name: /Street View/ })
    expect(link).toHaveAttribute(
      'href',
      'https://www.google.com/maps/@?api=1&map_action=pano&viewpoint=47.500500,19.040000&heading=0&pitch=0',
    )
    expect(link).toHaveAttribute('target', '_blank')
    expect(link).toHaveAttribute('rel', 'noopener noreferrer')
  })

  it('handles an unrated segment', () => {
    renderCard({ rqi: null, score: null, pBad: null })
    expect(screen.getByTestId('segment-quality')).toHaveTextContent('Nincs adat')
    expect(screen.getByTestId('segment-quality')).not.toHaveTextContent('Pontszám')
    expect(screen.queryByTestId('segment-pbad')).not.toBeInTheDocument()
  })

  it('closes from the × button', () => {
    const onClose = vi.fn()
    renderCard({}, onClose)
    fireEvent.click(screen.getByRole('button', { name: 'Bezárás' }))
    expect(onClose).toHaveBeenCalledTimes(1)
  })

  it('steps aside on a phone while a frame card is open', () => {
    render(<SegmentDetailCard segment={segment()} onClose={() => {}} behind />)
    expect(screen.getByRole('region', { name: 'Útszakasz részletei' })).toHaveClass('road-card--behind')
  })
})
