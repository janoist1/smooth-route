import React, { type ReactNode } from 'react'

interface FormControlProps {
  children: ReactNode
  error?: string
  className?: string
  style?: React.CSSProperties
}

export const FormControl: React.FC<FormControlProps> = ({ children, error, className, style }) => {
  return (
    <div
      className={className}
      style={{
        display: 'flex',
        flexDirection: 'column',
        gap: '8px',
        width: '100%',
        marginTop: 'auto',
        ...style,
      }}>
      <div style={{ position: 'relative' }}>
        {children}

        {error && (
          <span
            style={{
              position: 'absolute',
              top: '100%',
              left: 0,
              marginTop: '4px',
              fontSize: '0.75rem',
              color: '#f87171',
            }}>
            {error}
          </span>
        )}
      </div>
    </div>
  )
}
