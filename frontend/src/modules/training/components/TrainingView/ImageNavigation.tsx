import React from 'react'
import { ChevronLeft, ChevronRight, X } from 'lucide-react'

interface ImageNavigationProps {
  hasPrev: boolean
  hasNext: boolean
  onPrev: () => void
  onNext: () => void
  onClose: () => void
}

export const ImageNavigation: React.FC<ImageNavigationProps> = ({
  hasPrev,
  hasNext,
  onPrev,
  onNext,
  onClose,
}) => {
  return (
    <>
      {/* Close Button */}
      <button
        onClick={onClose}
        style={{
          position: 'absolute',
          top: '20px',
          right: '20px',
          zIndex: 100,
          background: 'rgba(0, 0, 0, 0.6)',
          border: '1px solid #555',
          color: 'white',
          width: '36px',
          height: '36px',
          borderRadius: '50%',
          cursor: 'pointer',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          transition: 'background 0.2s',
        }}
        onMouseOver={e => (e.currentTarget.style.background = 'rgba(239, 68, 68, 0.8)')}
        onMouseOut={e => (e.currentTarget.style.background = 'rgba(0, 0, 0, 0.6)')}
        title="Close / Back to Map">
        <X size={20} />
      </button>

      {/* Prev Button */}
      {hasPrev && (
        <button
          onClick={onPrev}
          style={{
            position: 'absolute',
            left: '20px',
            top: '50%',
            transform: 'translateY(-50%)',
            background: 'rgba(0,0,0,0.5)',
            color: 'white',
            border: 'none',
            borderRadius: '50%',
            width: '48px',
            height: '48px',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            cursor: 'pointer',
            zIndex: 60,
            transition: 'background 0.2s',
          }}
          onMouseOver={e => (e.currentTarget.style.background = 'rgba(0,0,0,0.8)')}
          onMouseOut={e => (e.currentTarget.style.background = 'rgba(0,0,0,0.5)')}>
          <ChevronLeft size={32} />
        </button>
      )}

      {/* Next Button */}
      {hasNext && (
        <button
          onClick={onNext}
          style={{
            position: 'absolute',
            right: '20px',
            top: '50%',
            transform: 'translateY(-50%)',
            background: 'rgba(0,0,0,0.5)',
            color: 'white',
            border: 'none',
            borderRadius: '50%',
            width: '48px',
            height: '48px',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            cursor: 'pointer',
            zIndex: 60,
            transition: 'background 0.2s',
          }}
          onMouseOver={e => (e.currentTarget.style.background = 'rgba(0,0,0,0.8)')}
          onMouseOut={e => (e.currentTarget.style.background = 'rgba(0,0,0,0.5)')}>
          <ChevronRight size={32} />
        </button>
      )}
    </>
  )
}
