import React from 'react'
import { getRQIColor } from '../../ui'
import { STALE_AFTER_YEARS } from '../captureDate'
import type { RoadSegment } from '../segments/types'
import { pathMidpoint, streetViewUrl } from '../segments/geometry'
import {
  captureStaleness,
  confidenceExplanation,
  confidenceLabelHu,
  formatCaptureRange,
  formatLength,
  formatPercent,
  formatScore,
  highwayLabelHu,
  rqiLabelHu,
  segmentTitle,
} from '../segments/labels'
import './roadCards.css'

interface SegmentDetailCardProps {
  segment: RoadSegment
  onClose: () => void
  /** A frame's own card is open: on a phone this sheet steps aside for it. */
  behind?: boolean
}

const CONFIDENCE_STEPS: Record<string, number> = { low: 1, medium: 2, high: 3 }

/**
 * Detail card of one road segment. Pure presentation (everything comes from
 * the segment), no auth: it is the same for anonymous / read-only visitors.
 */
const SegmentDetailCard: React.FC<SegmentDetailCardProps> = ({ segment, onClose, behind }) => {
  const color = getRQIColor(segment.rqi)
  const title = segmentTitle(segment)
  const roadType = highwayLabelHu(segment.highway)
  // The road type is already the title of an unnamed road — don't repeat it.
  const subtitle = [segment.roadName?.trim() ? roadType : null, formatLength(segment.lengthM)]
    .filter(Boolean)
    .join(' · ')

  const steps = CONFIDENCE_STEPS[segment.confidenceLevel] ?? 0
  const staleness = captureStaleness(segment.captureDateMin, segment.captureDateMax)
  const midpoint = pathMidpoint(segment.path)

  return (
    <section
      className={`road-card${behind ? ' road-card--behind' : ''}`}
      aria-label="Útszakasz részletei"
      style={{ '--road-color': color } as React.CSSProperties}>
      <header className="road-card__header">
        <div style={{ minWidth: 0 }}>
          <h2 className="road-card__title">{title}</h2>
          <div className="road-card__subtitle" data-testid="segment-subtitle">
            {subtitle}
          </div>
        </div>
        <button className="road-card__close" onClick={onClose} aria-label="Bezárás">
          ×
        </button>
      </header>

      <div className="road-card__body">
        {/* Quality: class label + the continuous score behind it */}
        <div className="road-card__row" data-testid="segment-quality">
          <span className="road-badge">{rqiLabelHu(segment.rqi)}</span>
          {segment.score != null && (
            <span className="road-card__dim">
              Pontszám: <span className="road-card__strong">{formatScore(segment.score)}</span>{' '}
              (1 = kiváló, 4 = rossz)
            </span>
          )}
        </div>

        {segment.pBad != null && (
          <div data-testid="segment-pbad">
            <div className="road-card__row road-card__dim">
              <span>Rossz út valószínűsége</span>
              <span className="road-card__strong">{formatPercent(segment.pBad)}</span>
            </div>
            <div className="road-meter">
              <div
                style={{
                  width: formatPercent(segment.pBad),
                  background: segment.pBad >= 0.5 ? '#f87171' : '#34d399',
                }}
              />
            </div>
          </div>
        )}

        <div data-testid="segment-confidence">
          <div className="road-card__row">
            <span>
              Megbízhatóság:{' '}
              <span className="road-card__strong">
                {confidenceLabelHu(segment.confidenceLevel)}
              </span>{' '}
              <span className="road-card__dim">({formatPercent(segment.confidence)})</span>
            </span>
            <span className="road-confidence-steps" aria-hidden="true">
              {[1, 2, 3].map(step => (
                <span key={step} className={step <= steps ? 'is-on' : undefined} />
              ))}
            </span>
          </div>
          <div className="road-card__dim" style={{ marginTop: 2 }}>
            {confidenceExplanation(segment.confidenceLevel, segment.nImages)}
          </div>
        </div>

        {/* The estimate is as current as the Street View images it is based on. */}
        <div>
          <div data-testid="segment-capture">
            Képek készültek:{' '}
            <span
              className="road-card__strong"
              style={staleness === 'all' ? { color: '#fbbf24' } : undefined}>
              {formatCaptureRange(segment.captureDateMin, segment.captureDateMax)}
            </span>
          </div>
          {staleness === 'all' && (
            <div role="note" className="road-note" style={{ marginTop: 8 }}>
              ⚠️ {STALE_AFTER_YEARS} évnél régebbi képek — az út állapota azóta változhatott.
            </div>
          )}
          {staleness === 'some' && (
            <div className="road-card__dim" style={{ marginTop: 4 }} data-testid="segment-partly-stale">
              A képek egy része {STALE_AFTER_YEARS} évnél régebbi.
            </div>
          )}
        </div>

        {midpoint && (
          <a
            className="road-link"
            href={streetViewUrl(midpoint.lat, midpoint.lng, midpoint.heading)}
            target="_blank"
            rel="noopener noreferrer">
            <span aria-hidden="true">🛣️</span> Megnyitás Street View-ban
          </a>
        )}
      </div>
    </section>
  )
}

export default SegmentDetailCard
