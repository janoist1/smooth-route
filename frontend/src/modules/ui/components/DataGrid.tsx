import { type ReactNode } from 'react'
import { Loader2 } from 'lucide-react'

export interface ColumnDef<T> {
  key: string
  header: string
  render: (item: T) => ReactNode
  width?: string
  align?: 'left' | 'center' | 'right'
}

interface DataGridProps<T> {
  columns: ColumnDef<T>[]
  data: T[]
  onRowClick?: (item: T) => void
  loading?: boolean
  emptyMessage?: ReactNode
}

export const DataGrid = <T,>({ 
  columns, 
  data, 
  onRowClick,
  loading,
  emptyMessage = 'No data found'
}: DataGridProps<T>) => {
  
  if (loading) {
    return (
      <div style={{ display: 'flex', justifyContent: 'center', padding: '60px' }}>
        <Loader2 className="spinner" size={32} color="#3b82f6" />
        <style>{`
          .spinner { animation: spin 1s linear infinite; }
          @keyframes spin { 100% { transform: rotate(360deg); } }
        `}</style>
      </div>
    )
  }

  if (data.length === 0) {
    return (
      <div style={{ padding: '60px', textAlign: 'center', color: '#6b7280', background: 'rgba(255,255,255,0.02)', borderRadius: '16px', border: '1px solid rgba(255,255,255,0.05)' }}>
        {emptyMessage}
      </div>
    )
  }

  return (
    <div style={{ overflowX: 'auto', borderRadius: '16px', border: '1px solid rgba(255, 255, 255, 0.1)' }}>
      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.875rem' }}>
        <thead>
          <tr style={{ background: 'rgba(17, 24, 39, 0.8)', color: '#9ca3af', textAlign: 'left' }}>
            {columns.map((col) => (
              <th 
                key={col.key}
                style={{ 
                  padding: '16px', 
                  fontWeight: 600, 
                  borderBottom: '1px solid rgba(255, 255, 255, 0.05)',
                  width: col.width,
                  textAlign: col.align || 'left'
                }}
              >
                {col.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {data.map((item, index) => (
            <tr 
              key={index}
              onClick={() => onRowClick && onRowClick(item)}
              style={{ 
                borderBottom: index === data.length - 1 ? 'none' : '1px solid rgba(255, 255, 255, 0.05)',
                cursor: onRowClick ? 'pointer' : 'default',
                background: 'rgba(17, 24, 39, 0.4)',
                transition: 'background 0.2s'
              }}
              onMouseEnter={(e) => {
                 if (onRowClick) e.currentTarget.style.background = 'rgba(59, 130, 246, 0.1)'
              }}
              onMouseLeave={(e) => {
                 if (onRowClick) e.currentTarget.style.background = 'rgba(17, 24, 39, 0.4)'
              }}
            >
              {columns.map((col) => (
                <td 
                  key={col.key}
                  style={{ 
                    padding: '16px',
                    textAlign: col.align || 'left',
                    color: '#e5e7eb'
                  }}
                >
                  {col.render(item)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
