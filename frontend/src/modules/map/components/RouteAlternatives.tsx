import React from 'react'
import { extraDurationLabel, formatDuration, type RouteAlternative } from '../alternatives'
import { formatKm, formatPercent } from '../segments/labels'
import { summarizeRouteQuality } from '../segments/routeSummary'

interface RouteAlternativesProps {
  routes: RouteAlternative[]
  selectedIndex: number | null
  onSelect: (index: number) => void
}

const badge = (bg: string): React.CSSProperties => ({
  background: bg,
  color: '#fff',
  borderRadius: 999,
  padding: '1px 8px',
  fontSize: 11,
  fontWeight: 700,
  whiteSpace: 'nowrap',
})

/**
 * Google's alternative routes as selectable cards: time, distance, a quality
 * bar (same classes/colours as the route-quality card) and how much of the
 * route is measured. "Legsimább" / "Leggyorsabb" come from the backend
 * ranking (smoothest = best quality within +20 % time, enough coverage).
 */
const RouteAlternatives: React.FC<RouteAlternativesProps> = ({ routes, selectedIndex, onSelect }) => {
  if (routes.length < 2) return null
  const fastest = routes.find(r => r.isFastest)
  return (
    <section aria-label="Útvonal-változatok" style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
      {routes.map(route => {
        const summary = summarizeRouteQuality(route.quality)
        const selected = route.index === selectedIndex
        const extra = extraDurationLabel(route, fastest)
        return (
          <button
            key={route.index}
            type="button"
            onClick={() => onSelect(route.index)}
            aria-pressed={selected}
            data-testid={`route-alt-${route.index}`}
            style={{
              textAlign: 'left',
              padding: '8px 10px',
              borderRadius: 8,
              border: selected ? '2px solid #3b82f6' : '1px solid rgba(255,255,255,0.12)',
              background: selected ? 'rgba(37,99,235,0.18)' : 'rgba(255,255,255,0.04)',
              color: '#e5e7eb',
              cursor: 'pointer',
              display: 'flex',
              flexDirection: 'column',
              gap: 4,
              fontFamily: 'inherit',
            }}>
            <span style={{ display: 'flex', gap: 6, alignItems: 'center', flexWrap: 'wrap' }}>
              <strong style={{ fontSize: 15 }}>{formatDuration(route.durationS)}</strong>
              <span style={{ fontSize: 12, color: '#94a3b8' }}>
                {formatKm(route.distanceM)}
                {extra && ` · ${extra}`}
              </span>
              <span style={{ marginLeft: 'auto', display: 'flex', gap: 4 }}>
                {route.isSmoothest && <span style={badge('#16a34a')}>Legsimább</span>}
                {route.isFastest && <span style={badge('#2563eb')}>Leggyorsabb</span>}
              </span>
            </span>
            {route.summary && (
              <span style={{ fontSize: 12, color: '#94a3b8', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                {route.summary}
              </span>
            )}
            <span
              role="img"
              aria-label={summary.hasData ? `Átlag: ${summary.meanLabel}` : 'Nincs adat'}
              style={{ display: 'flex', height: 6, borderRadius: 3, overflow: 'hidden', background: 'rgba(255,255,255,0.15)' }}>
              {summary.classes
                .filter(c => c.share > 0)
                .map(c => (
                  <span key={c.rqi} style={{ width: `${(c.share * 100).toFixed(2)}%`, background: c.color }} />
                ))}
            </span>
            <span style={{ fontSize: 12, color: '#cbd5e1' }}>
              {summary.hasData ? (
                <>
                  Átlag: <b style={{ color: summary.meanColor }}>{summary.meanLabel}</b>
                </>
              ) : (
                'Nincs minőségi adat'
              )}
              <span style={{ color: summary.lowCoverage || !summary.hasData ? '#fbbf24' : '#94a3b8' }}>
                {' · '}
                {formatPercent(route.coverage)} felmérve
              </span>
            </span>
          </button>
        )
      })}
    </section>
  )
}

export default RouteAlternatives
