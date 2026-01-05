import React, { type ReactNode } from 'react'

export type StatTheme = 'blue' | 'yellow' | 'green' | 'red' | 'neutral'

interface StatCardProps {
  label: string
  value: string | number
  subtext?: ReactNode
  icon?: ReactNode
  theme?: StatTheme
}

const themeStyles: Record<
  StatTheme,
  { bg: string; border: string; iconColor: string; valueColor: string; subtextColor: string }
> = {
  neutral: {
    bg: 'rgba(255, 255, 255, 0.05)',
    border: 'rgba(255, 255, 255, 0.1)',
    iconColor: '#9ca3af',
    valueColor: 'white',
    subtextColor: '#6b7280',
  },
  blue: {
    bg: 'rgba(59, 130, 246, 0.1)',
    border: 'rgba(59, 130, 246, 0.2)',
    iconColor: '#60a5fa',
    valueColor: '#60a5fa',
    subtextColor: '#93c5fd',
  },
  yellow: {
    bg: 'rgba(234, 179, 8, 0.1)',
    border: 'rgba(234, 179, 8, 0.2)',
    iconColor: '#facc15',
    valueColor: '#facc15',
    subtextColor: '#fde047',
  },
  green: {
    bg: 'rgba(16, 185, 129, 0.1)',
    border: 'rgba(16, 185, 129, 0.2)',
    iconColor: '#34d399',
    valueColor: '#34d399',
    subtextColor: '#6ee7b7',
  },
  red: {
    bg: 'rgba(239, 68, 68, 0.1)',
    border: 'rgba(239, 68, 68, 0.2)',
    iconColor: '#f87171',
    valueColor: '#f87171',
    subtextColor: '#fca5a5',
  },
}

export const StatCard: React.FC<StatCardProps> = ({
  label,
  value,
  subtext,
  icon,
  theme = 'neutral',
}) => {
  const styles = themeStyles[theme]

  return (
    <div
      style={{
        background: styles.bg,
        borderRadius: '16px',
        padding: '20px',
        display: 'flex',
        flexDirection: 'column',
        gap: '8px',
        border: `1px solid ${styles.border}`,
      }}>
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: '8px',
          color: styles.iconColor,
          fontSize: '0.875rem',
        }}>
        {icon} {label}
      </div>
      <div style={{ fontSize: '2rem', fontWeight: 'bold', color: styles.valueColor }}>{value}</div>
      {subtext && <div style={{ fontSize: '0.75rem', color: styles.subtextColor }}>{subtext}</div>}
    </div>
  )
}

export const StatsGrid: React.FC<{ children: ReactNode }> = ({ children }) => {
  return (
    <div
      style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(4, 1fr)',
        gap: '16px',
        marginBottom: '32px',
      }}>
      {children}
    </div>
  )
}
