import React from 'react'
import { STALE_AFTER_YEARS } from '../captureDate'

interface StaleImageToggleProps {
  enabled: boolean
  onChange: (enabled: boolean) => void
}

// Map filter: dim points whose Street View image is older than the threshold,
// so the user sees where the shown quality may be outdated.
const StaleImageToggle: React.FC<StaleImageToggleProps> = ({ enabled, onChange }) => (
  <label
    className="glass-panel"
    title={`${STALE_AFTER_YEARS} évnél régebbi Street View-képből becsült pontok halványítása`}
    style={{
      position: 'absolute',
      bottom: '100px',
      right: '30px',
      zIndex: 1000,
      padding: '8px 12px',
      borderRadius: '12px',
      display: 'flex',
      alignItems: 'center',
      gap: '8px',
      background: 'var(--bg-panel)',
      backdropFilter: 'blur(10px)',
      border: 'var(--glass-border)',
      boxShadow: 'var(--glass-shadow)',
      color: 'var(--text-main)',
      fontSize: '0.85rem',
      cursor: 'pointer',
      userSelect: 'none',
    }}>
    <input type="checkbox" checked={enabled} onChange={e => onChange(e.target.checked)} />
    Régi képek halványítása (&gt;{STALE_AFTER_YEARS} év)
  </label>
)

export default StaleImageToggle
