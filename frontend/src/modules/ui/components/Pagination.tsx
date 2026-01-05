import React from 'react'
import { ChevronLeft, ChevronRight, ChevronsLeft, ChevronsRight } from 'lucide-react'

interface PaginationProps {
  currentPage: number
  totalPages: number
  onPageChange: (page: number) => void
  disabled?: boolean
}

export const Pagination: React.FC<PaginationProps> = ({
  currentPage,
  totalPages,
  onPageChange,
  disabled = false,
}) => {
  const isFirst = currentPage === 1
  const isLast = currentPage === totalPages

  const handlePageChange = (page: number) => {
    if (page >= 1 && page <= totalPages && !disabled) {
      onPageChange(page)
    }
  }

  // Generate page numbers to show
  const getPageNumbers = () => {
    const delta = 2
    const range = []
    const rangeWithDots = []
    let l

    for (let i = 1; i <= totalPages; i++) {
        if (i === 1 || i === totalPages || (i >= currentPage - delta && i <= currentPage + delta)) {
            range.push(i)
        }
    }

    for (const i of range) {
        if (l) {
            if (i - l === 2) {
                rangeWithDots.push(l + 1)
            } else if (i - l !== 1) {
                rangeWithDots.push('...')
            }
        }
        rangeWithDots.push(i)
        l = i
    }
    return rangeWithDots
  }

  const btnStyle: React.CSSProperties = {
     display: 'flex',
     alignItems: 'center',
     justifyContent: 'center',
     width: '32px',
     height: '32px',
     borderRadius: '8px',
     border: '1px solid transparent', // Changed from visible border to transparent
     background: 'rgba(255,255,255,0.05)',
     color: '#9ca3af', // Dimmer text for inactive
     cursor: 'pointer',
     transition: 'all 0.2s',
     margin: '0 2px'
  }

  const activeBtnStyle: React.CSSProperties = {
     ...btnStyle,
     background: 'rgba(59, 130, 246, 0.2)',
     border: '1px solid #3b82f6', // Explicit active border
     color: '#60a5fa',
     fontWeight: 'bold'
  }

  const disabledBtnStyle: React.CSSProperties = {
      ...btnStyle,
      opacity: 0.5,
      cursor: 'not-allowed',
      background: 'transparent'
  }

  const dotsStyle: React.CSSProperties = {
     ...btnStyle,
     border: 'none',
     background: 'transparent',
     cursor: 'default' 
  }

  if (totalPages <= 1) return null

  return (
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '4px', marginTop: '24px' }}>
      <button
        onClick={() => handlePageChange(1)}
        disabled={isFirst || disabled}
        style={isFirst || disabled ? disabledBtnStyle : btnStyle}
      >
        <ChevronsLeft size={16} />
      </button>
      <button
        onClick={() => handlePageChange(currentPage - 1)}
        disabled={isFirst || disabled}
        style={isFirst || disabled ? disabledBtnStyle : btnStyle}
      >
        <ChevronLeft size={16} />
      </button>

      {getPageNumbers().map((p, i) => (
         <button
            key={i}
            onClick={() => typeof p === 'number' ? handlePageChange(p) : undefined}
            disabled={disabled || p === '...'}
            style={p === currentPage ? activeBtnStyle : (p === '...' ? dotsStyle : btnStyle)}
         >
            {p}
         </button>
      ))}

      <button
        onClick={() => handlePageChange(currentPage + 1)}
        disabled={isLast || disabled}
        style={isLast || disabled ? disabledBtnStyle : btnStyle}
      >
        <ChevronRight size={16} />
      </button>
      <button
        onClick={() => handlePageChange(totalPages)}
        disabled={isLast || disabled}
        style={isLast || disabled ? disabledBtnStyle : btnStyle}
      >
        <ChevronsRight size={16} />
      </button>

      <div style={{ marginLeft: '12px', fontSize: '12px', color: '#9ca3af' }}>
          Page {currentPage} of {totalPages}
      </div>
    </div>
  )
}
