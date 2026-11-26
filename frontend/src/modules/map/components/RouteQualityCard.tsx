import React from 'react'
import { getRQIColor } from '../../ui'
import type { RoadSegment, RouteQuality } from '../segments/types'
import {
  formatKm,
  formatLength,
  formatPercent,
  formatScore,
  rqiLabelHu,
  segmentTitle,
} from '../segments/labels'
import { summarizeRouteQuality } from '../segments/routeSummary'
import './roadCards.css'

interface RouteQualityCardProps {
  quality: RouteQuality | null
  loading: boolean
  error: string | null
  /** A "worst segment" was clicked: show it on the map. */
  onSelectSegment: (segment: RoadSegment) => void
}

/** How many of the worst segments the compact card lists. */
const MAX_WORST = 5

const roadColor = (color: string) => ({ '--road-color': color }) as React.CSSProperties

/**
 * Compact quality summary of the planned route: length, measured share, a
 * stacked bar of the length per quality class, the length-weighted average
 * and the worst segments. Pure presentation — numbers come from
 * summarizeRouteQuality.
 */
const RouteQualityCard: React.FC<RouteQualityCardProps> = ({
  quality,
  loading,
  error,
  onSelectSegment,
}) => {
  if (loading) {
    return (
      <section className="route-quality" aria-label="Útvonal minősége" aria-busy="true">
        <h4 className="route-quality__title">Útvonal minősége</h4>
        <div className="road-card__dim">Útminőség számítása…</div>
      </section>
    )
  }

  if (error) {
    return (
      <section className="route-quality" aria-label="Útvonal minősége">
        <h4 className="route-quality__title">Útvonal minősége</h4>
        <div role="alert" style={{ color: '#fca5a5' }}>
          Az útvonal minősége most nem érhető el.
        </div>
      </section>
    )
  }

  if (!quality) return null

  const summary = summarizeRouteQuality(quality)
  const worst = (quality.worstSegments ?? []).slice(0, MAX_WORST)

  return (
    <section className="route-quality" aria-label="Útvonal minősége">
      <h4 className="route-quality__title">Útvonal minősége</h4>

      <div className="route-quality__stats">
        <div data-testid="route-total">
          <div className="route-quality__stat-value">{formatKm(summary.totalLengthM)}</div>
          <div className="road-card__dim">teljes hossz</div>
        </div>
        <div data-testid="route-coverage" style={{ textAlign: 'right' }}>
          <div className="route-quality__stat-value">{formatPercent(summary.coverage)}</div>
          <div className="road-card__dim">
            felmérve{summary.hasData ? ` (${formatKm(summary.coveredLengthM)})` : ''}
          </div>
        </div>
      </div>

      {!summary.hasData ? (
        <div className="route-quality__empty" role="status">
          <strong>Nincs adat erre az útvonalra.</strong>
          <div className="road-card__dim" style={{ marginTop: 2 }}>
            Az útvonal menti utakat még nem mértük fel, ezért a minőségéről nem tudunk mit mondani.
          </div>
        </div>
      ) : (
        <>
          <div
            className="route-quality__bar"
            role="img"
            aria-label={
              summary.classes
                .filter(c => c.lengthM > 0)
                .map(c => `${c.label}: ${formatKm(c.lengthM)}`)
                .join(', ') +
              (summary.unknownShare > 0.005 ? `, nincs adat: ${formatPercent(summary.unknownShare)}` : '')
            }>
            {summary.classes
              .filter(c => c.share > 0)
              .map(c => (
                <span
                  key={c.rqi}
                  data-testid={`route-bar-${c.key}`}
                  title={`${c.label}: ${formatKm(c.lengthM)}`}
                  style={{ width: `${(c.share * 100).toFixed(2)}%`, background: c.color }}
                />
              ))}
          </div>

          <ul className="route-quality__legend">
            {summary.classes
              .filter(c => c.lengthM > 0)
              .map(c => (
                <li key={c.rqi} data-testid={`route-class-${c.key}`}>
                  <span className="route-quality__dot" style={roadColor(c.color)} />
                  {c.label} {formatKm(c.lengthM)}
                </li>
              ))}
            {summary.unknownShare > 0.005 && (
              <li data-testid="route-class-unknown">
                <span className="route-quality__dot" style={roadColor('rgba(255,255,255,0.25)')} />
                nincs adat {formatPercent(summary.unknownShare)}
              </li>
            )}
          </ul>

          <div data-testid="route-mean">
            Átlagos minőség:{' '}
            <span
              className="road-badge"
              data-testid="route-mean-badge"
              style={roadColor(summary.meanColor)}>
              {summary.meanLabel}
            </span>{' '}
            <span className="road-card__dim">({formatScore(summary.meanScore)}, hosszal súlyozva)</span>
          </div>

          {summary.lowCoverage && (
            <div role="note" className="road-note">
              Az útvonalnak csak kis része felmért — az átlag csak erre a részre vonatkozik.
            </div>
          )}

          {worst.length > 0 && (
            <div>
              <div className="road-card__dim" style={{ marginBottom: 4 }}>
                Legrosszabb szakaszok
              </div>
              <ul className="route-quality__worst">
                {worst.map(segment => (
                  <li key={segment.id}>
                    <button
                      type="button"
                      style={roadColor(getRQIColor(segment.rqi))}
                      title="Megmutatás a térképen"
                      onClick={() => onSelectSegment(segment)}>
                      <span className="route-quality__worst-name">{segmentTitle(segment)}</span>
                      <span className="road-card__dim">{formatLength(segment.lengthM)}</span>
                      <span className="road-card__strong">{rqiLabelHu(segment.rqi)}</span>
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </>
      )}
    </section>
  )
}

export default RouteQualityCard
