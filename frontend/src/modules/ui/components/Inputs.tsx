import React from 'react'

interface InputProps extends Omit<React.InputHTMLAttributes<HTMLInputElement>, 'onChange'> {
  value: string | number
  onChange: (value: string | number) => void
  error?: boolean
}

const inputStyle: React.CSSProperties = {
  width: '100%',
  background: 'rgba(0, 0, 0, 0.2)',
  borderWidth: '1px',
  borderStyle: 'solid',
  borderColor: 'rgba(255, 255, 255, 0.1)',
  borderRadius: '12px',
  padding: '10px 14px',
  color: 'white',
  fontSize: '0.875rem',
  outline: 'none',
  transition: 'all 0.2s cubic-bezier(0.4, 0, 0.2, 1)',
  boxShadow: 'inset 0 2px 4px rgba(0,0,0,0.1)',
  boxSizing: 'border-box',
}

const inputFocusStyle: React.CSSProperties = {
  borderColor: '#3b82f6',
  background: 'rgba(0, 0, 0, 0.3)',
  boxShadow: '0 0 0 3px rgba(59, 130, 246, 0.15), inset 0 2px 4px rgba(0,0,0,0.1)',
}

export const TextInput: React.FC<InputProps> = ({ value, onChange, error, style, ...props }) => {
  const [focused, setFocused] = React.useState(false)

  return (
    <input
      {...props}
      type="text"
      value={value}
      onChange={e => onChange(e.target.value)}
      onFocus={e => {
        setFocused(true)
        props.onFocus?.(e)
      }}
      onBlur={e => {
        setFocused(false)
        props.onBlur?.(e)
      }}
      style={{
        ...inputStyle,
        ...(focused ? inputFocusStyle : {}),
        ...(error ? { borderColor: '#ef4444' } : {}),
        ...style,
      }}
    />
  )
}

export const NumberInput: React.FC<InputProps> = ({ value, onChange, error, style, ...props }) => {
  const [focused, setFocused] = React.useState(false)

  return (
    <input
      {...props}
      type="number"
      value={value}
      onChange={e => onChange(parseFloat(e.target.value))}
      onFocus={e => {
        setFocused(true)
        props.onFocus?.(e)
      }}
      onBlur={e => {
        setFocused(false)
        props.onBlur?.(e)
      }}
      style={{
        ...inputStyle,
        ...(focused ? inputFocusStyle : {}),
        ...(error ? { borderColor: '#ef4444' } : {}),
        ...style,
      }}
    />
  )
}

interface SelectProps extends Omit<React.SelectHTMLAttributes<HTMLSelectElement>, 'onChange'> {
  value: string | number
  onChange: (value: string) => void
  options: { value: string | number; label: string }[]
  error?: boolean
}

export const Select: React.FC<SelectProps> = ({
  value,
  onChange,
  options,
  error,
  style,
  ...props
}) => {
  const [focused, setFocused] = React.useState(false)

  return (
    <select
      {...props}
      value={value}
      onChange={e => onChange(e.target.value)}
      onFocus={e => {
        setFocused(true)
        props.onFocus?.(e)
      }}
      onBlur={e => {
        setFocused(false)
        props.onBlur?.(e)
      }}
      style={{
        ...inputStyle,
        ...(focused ? inputFocusStyle : {}),
        ...(error ? { borderColor: '#ef4444' } : {}),
        cursor: 'pointer',
        appearance: 'none',
        background: `rgba(0, 0, 0, 0.2) url("data:image/svg+xml;charset=UTF-8,%3Csvg%20xmlns%3D%22http%3A%2F%2Fwww.w3.org%2F2000%2Fsvg%22%20width%3D%2224%22%20height%3D%2224%22%20viewBox%3D%220%200%2024%2024%20fill%3D%22none%22%20stroke%3D%22%239ca3af%22%20stroke-width%3D%222%22%20stroke-linecap%3D%22round%22%20stroke-linejoin%3D%22round%22%3E%3Cpolyline%20points%3D%226%209%2012%2015%2018%209%22%3E%3C%2Fpolyline%3E%3C%2Fsvg%3E") no-repeat right 12px center`,
        backgroundSize: '16px',
        paddingRight: '40px',
        ...style,
      }}>
      {options.map(opt => (
        <option key={opt.value} value={opt.value} style={{ background: '#1f2937', color: 'white' }}>
          {opt.label}
        </option>
      ))}
    </select>
  )
}
