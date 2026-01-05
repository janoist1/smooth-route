import { type ReactNode } from 'react'

interface SegmentedControlOption {
  value: string
  label: string
  icon?: ReactNode
}

interface SegmentedControlProps {
  options: SegmentedControlOption[]
  value: string
  onChange: (value: string) => void
}

export const SegmentedControl: React.FC<SegmentedControlProps> = ({ options, value, onChange }) => {
  return (
    <div
      style={{
        display: 'inline-flex',
        background: 'rgba(255, 255, 255, 0.05)',
        padding: '4px',
        borderRadius: '12px',
        border: '1px solid rgba(255, 255, 255, 0.1)',
      }}>
      {options.map(option => (
        <button
          key={option.value}
          onClick={() => onChange(option.value)}
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '8px',
            padding: '8px 16px',
            borderRadius: '8px',
            border: 'none',
            fontSize: '0.875rem',
            fontWeight: 500,
            cursor: 'pointer',
            transition: 'all 0.2s',
            background: value === option.value ? '#3b82f6' : 'transparent',
            color: value === option.value ? 'white' : '#9ca3af',
          }}>
          {option.icon}
          {option.label}
        </button>
      ))}
    </div>
  )
}
