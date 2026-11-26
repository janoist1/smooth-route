import { describe, it, expect, vi, beforeAll, afterAll, afterEach } from 'vitest'
import { cleanup, render, screen } from '@testing-library/react'
import PointDetailCard from './PointDetailCard'
import type { RoadPointDetail } from '../types'

// The card only needs these two module hooks; stub them so the test needs no
// Redux store or Clerk provider.
vi.mock('../../auth', () => ({ useViewer: () => ({ isAdmin: false }) }))
vi.mock('../../settings/hooks', () => ({ useRqiDisplaySource: () => 'dino' }))

const detail = (capture_date: string | null): RoadPointDetail => ({
  id: 1,
  latitude: 47.5,
  longitude: 19.0,
  rqi_score: 2,
  dino_rqi_score: 2,
  image_url: '',
  damage_count: 0,
  created_at: '2026-01-05T10:00:00',
  capture_date,
})

const renderCard = (capture: string | null) =>
  render(<PointDetailCard detail={detail(capture)} loading={false} onClose={() => {}} onTrain={() => {}} />)

describe('PointDetailCard capture date', () => {
  beforeAll(() => {
    vi.useFakeTimers({ toFake: ['Date'] })
    vi.setSystemTime(new Date(2026, 10, 18))
  })
  afterAll(() => vi.useRealTimers())
  afterEach(cleanup)

  it('shows the capture month and warns when the image is older than 4 years', () => {
    renderCard('2019-06')
    expect(screen.getByTestId('capture-date')).toHaveTextContent('Kép készült: 2019-06 (7 éves)')
    expect(screen.getByRole('note')).toHaveTextContent('4 évnél régebbi kép')
  })

  it('does not warn for a recent image', () => {
    renderCard('2025-08')
    expect(screen.getByTestId('capture-date')).toHaveTextContent('Kép készült: 2025-08 (1 éves)')
    expect(screen.queryByRole('note')).not.toBeInTheDocument()
  })

  it('says unknown (and does not warn) without a capture date', () => {
    renderCard(null)
    expect(screen.getByTestId('capture-date')).toHaveTextContent('Kép készült: ismeretlen')
    expect(screen.queryByRole('note')).not.toBeInTheDocument()
  })
})
