import React from 'react'
import { Settings } from 'lucide-react'

const SettingsHeader: React.FC = () => {
  return (
    <header style={{ marginBottom: '48px' }}>
      <div style={{ maxWidth: '800px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '16px', marginBottom: '12px' }}>
          <div
            style={{
              width: '48px',
              height: '48px',
              borderRadius: '14px',
              background: 'rgba(59, 130, 246, 0.15)',
              color: '#60a5fa',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
            }}>
            <Settings size={28} />
          </div>
          <h1
            style={{
              fontSize: '2.5rem',
              fontWeight: 800,
              color: 'white',
              letterSpacing: '-0.02em',
            }}>
            Rendszerbeállítások
          </h1>
        </div>
        <p style={{ color: '#9ca3af', fontSize: '1.1rem', maxWidth: '600px', lineHeight: 1.5 }}>
          Itt konfigurálhatod az élő elemzőkomponensek és az adatgyűjtés beállításait.
        </p>
      </div>
    </header>
  )
}

export default SettingsHeader
