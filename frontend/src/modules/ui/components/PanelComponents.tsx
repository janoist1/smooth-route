import React, { type ReactNode } from 'react'

// --- Glass Panel ---
interface GlassPanelProps {
  children: ReactNode
  className?: string
  style?: React.CSSProperties
}

export const GlassPanel: React.FC<GlassPanelProps> = ({ children, style, className }) => {
  return (
    <div 
      className={className}
      style={{
        background: 'rgba(17, 24, 39, 0.4)',
        padding: '24px',
        borderRadius: '24px',
        border: '1px solid rgba(255, 255, 255, 0.1)',
        backdropFilter: 'blur(16px)',
        boxShadow: '0 8px 32px rgba(0, 0, 0, 0.3)',
        ...style
      }}
    >
      {children}
    </div>
  )
}

// --- Selection Button ---
interface SelectionButtonProps {
  selected: boolean
  onClick: () => void
  icon: ReactNode
  label: string
  subtext?: string
  color?: 'blue' | 'purple' | 'orange' | 'green'
}

export const SelectionButton: React.FC<SelectionButtonProps> = ({ selected, onClick, icon, label, subtext, color = 'blue' }) => {
  const colors = {
    blue: { border: '#3b82f6', bg: 'rgba(59, 130, 246, 0.2)', text: '#60a5fa' },
    purple: { border: '#8b5cf6', bg: 'rgba(139, 92, 246, 0.2)', text: '#a78bfa' },
    orange: { border: '#f59e0b', bg: 'rgba(245, 158, 11, 0.2)', text: '#fbbf24' },
    green: { border: '#10b981', bg: 'rgba(16, 185, 129, 0.2)', text: '#34d399' }
  }
  
  const activeColor = colors[color]

  return (
    <button 
      onClick={onClick}
      style={{
        padding: '12px',
        borderRadius: '12px',
        border: '1px solid',
        borderColor: selected ? activeColor.border : 'rgba(255,255,255,0.1)',
        background: selected ? activeColor.bg : 'rgba(255,255,255,0.02)',
        color: selected ? activeColor.text : '#9ca3af',
        transition: 'all 0.2s',
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        gap: '4px',
        cursor: 'pointer',
        width: '100%',
        textAlign: 'center'
      }}
    >
      <div style={{ marginBottom: '4px' }}>{icon}</div>
      <span style={{ fontSize: '0.75rem', fontWeight: 600 }}>{label}</span>
      {subtext && <div style={{ fontSize: '0.65rem', color: '#9ca3af', lineHeight: 1.2 }}>{subtext}</div>}
    </button>
  )
}

// --- Status Bar --- (Different from TopProgressBar, this is for inside panels)
interface ProgressBarProps {
  progress: number
  total: number
  label?: string
  colorStart?: string
  colorEnd?: string
}

export const ProgressBar: React.FC<ProgressBarProps> = ({ 
  progress, 
  total, 
  label, 
  colorStart = '#3b82f6', 
  colorEnd = '#60a5fa' 
}) => {
  const percentage = total > 0 
    ? (progress / total) * 100 
    : (progress > 0 ? 100 : 0)
  
  return (
    <div style={{ marginTop: '24px' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '8px' }}>
        <span style={{ fontSize: '0.875rem', fontWeight: 500, color: colorEnd }}>
          {label || 'Processing...'}
        </span>
        <span style={{ fontSize: '0.875rem', fontWeight: 'bold' }}>
          {Math.round(percentage)}%
        </span>
      </div>
      <div style={{ width: '100%', height: '8px', background: 'rgba(255,255,255,0.05)', borderRadius: '999px', overflow: 'hidden' }}>
        <div style={{ 
          height: '100%', 
          background: `linear-gradient(90deg, ${colorStart}, ${colorEnd})`, 
          width: `${percentage}%`,
          transition: 'width 0.3s ease-out'
        }} />
      </div>
      <div style={{ fontSize: '0.75rem', color: '#6b7280', marginTop: '6px' }}>
        {progress} / {total} processed
      </div>
    </div>
  )
}
