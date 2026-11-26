import React, { type ReactNode } from 'react'

export interface NavItem {
  path: string
  label: string
  icon: ReactNode
}

interface FloatingNavBarProps {
  items: NavItem[]
  currentPath: string
  onNavigate: (path: string) => void
  /** Extra content rendered after the nav pills (e.g. user menu). */
  trailing?: ReactNode
}

export const FloatingNavBar: React.FC<FloatingNavBarProps> = ({
  items,
  currentPath,
  onNavigate,
  trailing,
}) => {
  return (
    <div
      className="fnav"
      style={{
        position: 'fixed',
        zIndex: 9999,
        display: 'flex',
        flexWrap: 'nowrap',
        pointerEvents: 'none',
      }}>
      {/* Phone width: icon-only pills that never wrap (the admin row has 5
          items + the user menu and used to cover the planner and zoom). */}
      <style>{`
        .fnav { top: 24px; right: 24px; gap: 12px; }
        @media (max-width: 640px) {
          .fnav { top: 12px; right: 12px; gap: 6px; }
          .fnav .fnav-label { display: none; }
          .fnav .fnav-btn { padding: 9px !important; }
        }
      `}</style>
      {items.map(item => {
        const isActive = currentPath === item.path
        return (
          <button
            key={item.path}
            className="fnav-btn"
            aria-label={item.label}
            title={item.label}
            onClick={() => onNavigate(item.path)}
            style={{
              pointerEvents: 'auto',
              display: 'flex',
              alignItems: 'center',
              gap: '8px',
              padding: '10px 16px',
              borderRadius: '9999px',
              border: isActive
                ? '1px solid rgba(59, 130, 246, 0.5)'
                : '1px solid rgba(255, 255, 255, 0.1)',
              background: isActive ? 'rgba(37, 99, 235, 0.9)' : 'rgba(0, 0, 0, 0.4)',
              color: isActive ? 'white' : '#d1d5db',
              backdropFilter: 'blur(12px)',
              boxShadow: isActive
                ? '0 10px 15px -3px rgba(30, 58, 138, 0.4)'
                : '0 4px 6px -1px rgba(0, 0, 0, 0.1)',
              transition: 'all 0.3s ease-out',
              cursor: 'pointer',
              fontSize: '0.875rem',
              fontWeight: 500,
            }}
            onMouseEnter={e => {
              if (!isActive) {
                e.currentTarget.style.background = 'rgba(0, 0, 0, 0.6)'
                e.currentTarget.style.color = 'white'
                e.currentTarget.style.transform = 'scale(1.05)'
              }
            }}
            onMouseLeave={e => {
              if (!isActive) {
                e.currentTarget.style.background = 'rgba(0, 0, 0, 0.4)'
                e.currentTarget.style.color = '#d1d5db'
                e.currentTarget.style.transform = 'scale(1)'
              }
            }}>
            {item.icon}
            <span className="fnav-label">{item.label}</span>
          </button>
        )
      })}
      {trailing}
    </div>
  )
}
