import React from 'react'
import { Cpu } from 'lucide-react'
import { GlassPanel } from '../../ui'

interface AnalysisHubLayoutProps {
  title: string
  icon?: React.ReactNode
  configContent: React.ReactNode
  actionsContent: React.ReactNode
  statusContent: React.ReactNode
  statusBadge?: React.ReactNode
}

export const AnalysisHubLayout: React.FC<AnalysisHubLayoutProps> = ({
  title,
  icon,
  configContent,
  actionsContent,
  statusContent,
  statusBadge
}) => {
  return (
    <GlassPanel style={{ marginBottom: '40px' }}>
      {/* Header */}
      <div
        style={{
          marginBottom: '24px',
          display: 'flex',
          alignItems: 'center',
          gap: '12px',
          paddingBottom: '20px',
          borderBottom: '1px solid rgba(255, 255, 255, 0.05)',
        }}>
        <div
          style={{
            width: '32px',
            height: '32px',
            borderRadius: '8px',
            background: 'linear-gradient(135deg, #3b82f6, #8b5cf6)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            boxShadow: '0 4px 12px rgba(59, 130, 246, 0.3)',
          }}>
          {icon || <Cpu size={18} color="white" />}
        </div>
        <div>
          <h2 style={{ fontSize: '1.1rem', fontWeight: 'bold' }}>{title}</h2>
        </div>
      </div>

      {/* 2-Column Grid */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '32px' }}>
        {/* Left: Configuration & Actions */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
          <div>
            <label
              style={{
                display: 'block',
                fontSize: '0.85rem',
                fontWeight: 600,
                color: '#9ca3af',
                marginBottom: '8px',
                textTransform: 'uppercase',
                letterSpacing: '0.05em',
              }}>
              Configuration
            </label>
            <div
              style={{
                background: 'rgba(255,255,255,0.02)',
                padding: '16px',
                borderRadius: '12px',
                border: '1px solid rgba(255,255,255,0.05)',
                display: 'flex', 
                flexDirection: 'column',
                gap: '16px'
              }}>
              {configContent}
            </div>
          </div>
          
          {/* Actions (Buttons) */}
          <div style={{ display: 'flex', gap: '12px' }}>
            {actionsContent}
          </div>
        </div>

        {/* Right: Status */}
        <div style={{ display: 'flex', flexDirection: 'column' }}>
          <div
            style={{
              flex: 1,
              background: 'rgba(0,0,0,0.2)',
              borderRadius: '12px',
              padding: '16px',
              border: '1px solid rgba(255,255,255,0.05)',
              display: 'flex',
              flexDirection: 'column',
              minHeight: '200px',
            }}>
            <div
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                marginBottom: '16px',
                alignItems: 'flex-start',
              }}>
              <span
                style={{
                  fontSize: '0.75rem',
                  fontWeight: 'bold',
                  textTransform: 'uppercase',
                  letterSpacing: '0.05em',
                  color: '#60a5fa',
                }}>
                System Status
              </span>
              {statusBadge}
            </div>
            
            <div
              style={{
                flex: 1,
                display: 'flex',
                flexDirection: 'column',
                justifyContent: 'center',
              }}>
              {statusContent}
            </div>
          </div>
        </div>
      </div>
    </GlassPanel>
  )
}
