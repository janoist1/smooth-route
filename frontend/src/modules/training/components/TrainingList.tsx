import React from 'react'
import { DataGrid, type ColumnDef, Pagination } from '../../ui'
import { getRQIColor } from '../../ui'
import type { TrainingPoint } from '../types'
import { useRqiDisplaySource } from '../../settings'

interface TrainingListProps {
  items: TrainingPoint[]
  loading: boolean
  error?: string | null
  onItemClick: (id: string | number) => void
  currentPage: number
  totalPages: number
  onPageChange: (page: number) => void
  onRetry?: () => void
}

export const TrainingList: React.FC<TrainingListProps> = ({
  items,
  loading,
  error,
  onItemClick,
  currentPage,
  totalPages,
  onPageChange,
  onRetry,
}) => {
  const displaySource = useRqiDisplaySource()

  // --- Table Configuration ---
  const allColumns: ColumnDef<TrainingPoint>[] = [
    {
      key: 'image',
      header: 'Image',
      width: '100px',
      render: (item: TrainingPoint) => (
        <div
          style={{
            width: '80px',
            height: '60px',
            borderRadius: '4px',
            overflow: 'hidden',
            background: '#374151',
          }}>
          {item.imageUrl && (
            <img
              src={item.imageUrl.startsWith('/') ? item.imageUrl : `/${item.imageUrl}`}
              alt=""
              style={{ width: '100%', height: '100%', objectFit: 'cover' }}
            />
          )}
        </div>
      ),
    },
    {
      key: 'id',
      header: 'ID',
      width: '80px',
      render: (item: TrainingPoint) => <code style={{ color: '#9ca3af' }}>#{item.id}</code>,
    },
    {
      key: 'rqi',
      header: 'YOLO AI',
      render: (item: TrainingPoint) => {
        const val = item.rqiScore
        if (val === undefined || val === null) return <span style={{ color: '#6b7280' }}>-</span>
        const color = getRQIColor(val)
        return <span style={{ fontWeight: 'bold', color }}>{val.toFixed(1)}</span>
      },
    },
    {
      key: 'dino_rqi',
      header: 'DINO AI',
      render: (item: TrainingPoint) => {
        const val = item.dinoRqiScore
        if (val === undefined || val === null) return <span style={{ color: '#6b7280' }}>-</span>
        const color = getRQIColor(val)
        return <span style={{ fontWeight: 'bold', color }}>{val.toFixed(1)}</span>
      },
    },
    {
      key: 'dino_manual',
      header: 'Ground Truth',
      render: (item: TrainingPoint) => {
        if (item.manualRqi || item.manualRqi === 0) {
          return (
            <span style={{ color: '#e5e7eb', fontWeight: 500 }}>{item.manualRqi.toFixed(0)}</span>
          )
        }
        return <span style={{ color: '#6b7280', fontStyle: 'italic', fontSize: '11px' }}>Pending</span>
      },
    },
    {
      key: 'tags',
      header: 'Tags',
      render: (item: TrainingPoint) => (
        <div style={{ display: 'flex', gap: '4px', flexWrap: 'wrap' }}>
          {item.manualTags?.map((tag: string) => (
            <span
              key={tag}
              style={{
                padding: '2px 8px',
                borderRadius: '12px',
                background: 'rgba(59, 130, 246, 0.1)',
                color: '#60a5fa',
                fontSize: '11px',
                border: '1px solid rgba(59, 130, 246, 0.2)',
              }}>
              {tag}
            </span>
          ))}
          {!item.manualTags?.length && <span style={{ color: '#4b5563' }}>-</span>}
        </div>
      ),
    },
  ]

  const columns = allColumns.filter(col => {
      if (col.key === 'rqi') return displaySource === 'yolo' || displaySource === 'both'
      if (col.key === 'dino_rqi') return displaySource === 'dino' || displaySource === 'both'
      return true
  })

  if (error) {
    return (
      <div
        style={{
          padding: '40px',
          textAlign: 'center',
          background: 'rgba(239, 68, 68, 0.05)',
          borderRadius: '16px',
          border: '1px solid rgba(239, 68, 68, 0.2)',
        }}>
        <p style={{ color: '#f87171', marginBottom: '16px' }}>{error}</p>
        {onRetry && (
          <button
            onClick={onRetry}
            style={{
              padding: '8px 20px',
              borderRadius: '8px',
              background: '#ef4444',
              color: 'white',
              border: 'none',
              cursor: 'pointer',
            }}>
            Try Again
          </button>
        )}
      </div>
    )
  }

  return (
    <div style={{ padding: '20px 0' }}>
      <div style={{ marginBottom: '20px', display: 'flex', justifyContent: 'center' }}>
        <Pagination
          currentPage={currentPage}
          totalPages={totalPages}
          onPageChange={onPageChange}
          disabled={loading}
        />
      </div>

      <DataGrid
        columns={columns}
        data={items}
        loading={loading && items.length === 0}
        onRowClick={(item: TrainingPoint) => onItemClick(item.id)}
        emptyMessage="No training data found"
      />

      <div style={{ borderTop: '1px solid rgba(255,255,255,0.05)', paddingTop: '20px' }}>
        <Pagination
          currentPage={currentPage}
          totalPages={totalPages}
          onPageChange={onPageChange}
          disabled={loading}
        />
      </div>
    </div>
  )
}

export default TrainingList
