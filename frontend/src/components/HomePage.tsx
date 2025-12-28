import React from 'react'
import MapView from '../modules/map/components/MapView'

const HomePage: React.FC = () => {
  return (
    <>
      <main>
        <MapView />
      </main>
      {/* Floating UI Overlay for Legend */}
      <div
        style={{
          position: 'absolute',
          bottom: 30,
          left: 30,
          zIndex: 1000,
          pointerEvents: 'none',
        }}>
        <div
          style={{
            pointerEvents: 'auto',
            background: 'var(--bg-panel)',
            backdropFilter: 'blur(10px)',
            padding: '15px',
            borderRadius: '16px',
            border: 'var(--glass-border)',
            color: 'white',
            boxShadow: 'var(--glass-shadow)',
          }}>
          <h2 style={{ fontSize: '1.2rem', marginBottom: '5px' }}>Smooth Route</h2>
          <div style={{ display: 'flex', gap: '10px', fontSize: '0.8rem', color: '#ccc' }}>
            <span style={{ color: '#4ade80' }}>● Good</span>
            <span style={{ color: '#facc15' }}>● Fair</span>
            <span style={{ color: '#ef4444' }}>● Poor</span>
          </div>
        </div>
      </div>
    </>
  )
}

export default HomePage
