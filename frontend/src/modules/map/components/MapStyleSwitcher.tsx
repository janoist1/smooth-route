import React from 'react'

export type MapStyle = 'dark' | 'light' | 'satellite' | 'street'

interface MapStyleSwitcherProps {
  currentStyle: MapStyle
  onChange: (style: MapStyle) => void
}

const styles: { id: MapStyle; label: string; preview: string }[] = [
  { id: 'dark', label: 'Dark', preview: '#1a1a1a' },
  { id: 'light', label: 'Light', preview: '#f0f0f0' },
  { id: 'satellite', label: 'Satellite', preview: 'linear-gradient(135deg, #1b5e20, #4e342e)' },
  { id: 'street', label: 'Street', preview: '#e0e0e0' },
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
          style={{
            width: '40px',
            height: '40px',
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
