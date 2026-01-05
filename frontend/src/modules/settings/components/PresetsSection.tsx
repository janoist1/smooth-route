import React from 'react'
import { Sparkles, Info } from 'lucide-react'
import { GlassPanel } from '../../ui'
import { PRESETS } from '../presets'

interface PresetsSectionProps {
  onApply: (values: Record<string, unknown>) => void
}

const PresetsSection: React.FC<PresetsSectionProps> = ({ onApply }) => {
  const handleApplyPreset = (presetValues: Record<string, unknown>) => {
    if (
      window.confirm(
        'Biztosan alkalmazni akarod ezt a preset-et? Ez felülírja a kapcsolódó beállításokat.',
      )
    ) {
      onApply(presetValues)
    }
  }

  return (
    <section style={{ marginBottom: '64px' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '24px' }}>
        <div
          style={{
            color: '#60a5fa',
            padding: '8px',
            borderRadius: '10px',
            background: 'rgba(96, 165, 250, 0.1)',
          }}>
          <Sparkles size={18} />
        </div>
        <h2 style={{ fontSize: '1.25rem', fontWeight: 600, color: 'white' }}>
          Gyorsbeállítások (Presets)
        </h2>
      </div>
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))',
          gap: '20px',
        }}>
        {PRESETS.map(preset => (
          <GlassPanel
            key={preset.id}
            title={preset.name}
            description={preset.description}
            style={{
              padding: '24px',
              display: 'flex',
              flexDirection: 'column',
              gap: '16px',
              borderColor: 'rgba(255,255,255,0.05)',
              borderWidth: '1px',
              borderStyle: 'solid',
              height: '100%',
            }}>
            <button
              onClick={() => handleApplyPreset(preset.values)}
              style={{
                marginTop: 'auto',
                background: 'rgba(59, 130, 246, 0.1)',
                color: '#60a5fa',
                padding: '10px',
                borderRadius: '10px',
                border: '1px solid rgba(59, 130, 246, 0.2)',
                fontSize: '0.875rem',
                fontWeight: 600,
                transition: 'all 0.2s',
              }}
              className="preset-btn">
              Preset alkalmazása
            </button>
          </GlassPanel>
        ))}
      </div>
      <p
        style={{
          marginTop: '16px',
          color: '#6b7280',
          fontSize: '0.8rem',
          display: 'flex',
          alignItems: 'center',
          gap: '6px',
        }}>
        <Info size={14} />A preset alkalmazása azonnal módosítja a kapcsolódó értékeket és elmenti
        azokat a szerverre.
      </p>
    </section>
  )
}

export default PresetsSection
