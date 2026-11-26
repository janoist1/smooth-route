import React from 'react'

export type MapStyle = 'dark' | 'light' | 'satellite' | 'street'

interface MapStyleSwitcherProps {
  currentStyle: MapStyle
  onChange: (style: MapStyle) => void
}

const styles: { id: MapStyle; label: string; preview: string }[] = [
  { id: 'dark', label: 'Sötét térkép', preview: '#1a1a1a' },
  { id: 'light', label: 'Világos térkép', preview: '#f0f0f0' },
  { id: 'satellite', label: 'Műholdkép', preview: 'linear-gradient(135deg, #1b5e20, #4e342e)' },
  { id: 'street', label: 'Utcatérkép (OSM)', preview: '#e0e0e0' },
]

const MapStyleSwitcher: React.FC<MapStyleSwitcherProps> = ({ currentStyle, onChange }) => {
  return (
    <div
      className="glass-panel"
      style={{
        position: 'absolute',
        bottom: '30px',
        right: '30px',
        zIndex: 1000,
        padding: '8px',
        borderRadius: '12px',
        display: 'flex',
        gap: '8px',
        background: 'var(--bg-panel)', // Ensure we use the glass var
        backdropFilter: 'blur(10px)',
        border: 'var(--glass-border)',
        boxShadow: 'var(--glass-shadow)',
      }}>
      {styles.map(style => (
        <button
          key={style.id}
          onClick={() => onChange(style.id)}
          title={style.label}
          aria-label={style.label}
          aria-pressed={currentStyle === style.id}
          style={{
            // 44 px: comfortable touch target on phones.
            width: '44px',
            height: '44px',
            borderRadius: '8px',
            border:
              currentStyle === style.id ? '2px solid var(--primary)' : '1px solid transparent',
            background: style.preview,
            cursor: 'pointer',
            position: 'relative',
            overflow: 'hidden',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            color: currentStyle === style.id ? 'white' : 'transparent',
            fontSize: '20px',
            fontWeight: 'bold',
          }}>
          {currentStyle === style.id && '✓'}
        </button>
      ))}
    </div>
  )
}

export default MapStyleSwitcher
