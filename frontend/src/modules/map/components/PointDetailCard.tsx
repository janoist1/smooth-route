import React from 'react'
import type { RoadPointDetail } from '../types'
import { getRQIColor, getRQILabel, resolveRqi } from '../../ui'
import { useRqiDisplaySource } from '../../settings'

interface PointDetailCardProps {
  detail: RoadPointDetail
  loading: boolean
  onClose: () => void
  onTrain: (id: string | number, model?: 'yolo' | 'dino') => void
}

const PointDetailCard: React.FC<PointDetailCardProps> = ({ detail, loading, onClose, onTrain }) => {
  const displaySource = useRqiDisplaySource()
  const { score: displayScore, model: targetModel, label: sourceLabel } = resolveRqi(
    detail ?? {},
    displaySource,
  )

  // Loading State
  if (loading) {
    return (
      <div className="glass-panel" style={{ 
          position: 'absolute',
          bottom: '180px',
          left: '30px',
          padding: '20px', 
          minWidth: '300px',
          background: 'var(--bg-panel)',
          backdropFilter: 'blur(12px)',
          borderRadius: '16px',
          border: 'var(--glass-border)',
          zIndex: 1000
      }}>
        <p>Loading details...</p>
      </div>
    )
  }

  if (!detail) return null

  // Use proxy for image path directly (it already includes /api prefix from backend)
  const imgUrl = detail.image_path || detail.image_url

  return (
    <div
      className="glass-panel"
      style={{
        position: 'absolute',
        bottom: '180px', // Moved up to avoid overlap
        left: '30px',
        width: '300px',
        padding: '0',
        overflow: 'hidden',
        zIndex: 1000,
        background: 'var(--bg-panel)',
        backdropFilter: 'blur(12px)',
        borderRadius: '16px',
        border: 'var(--glass-border)',
        boxShadow: 'var(--glass-shadow)',
        color: 'var(--text-main)',
        animation: 'slideUp 0.3s ease-out',
      }}>
      <div style={{ position: 'relative', height: '200px', background: '#000' }}>
        {imgUrl ? (
          <img
            src={imgUrl}
            alt="Road Surface"
            style={{ width: '100%', height: '100%', objectFit: 'cover' }}
            onError={e => {
              ;(e.target as HTMLImageElement).src =
                'https://placehold.co/600x400/1a1a1a/FFF?text=No+Image'
            }}
          />
        ) : (
          <div
            style={{
              width: '100%',
              height: '100%',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              color: '#666',
            }}>
            No Image Available
          </div>
        )}

        <button
          onClick={onClose}
          style={{
            position: 'absolute',
            top: 10,
            right: 10,
            background: 'rgba(0,0,0,0.5)',
            color: 'white',
            width: '32px',
            height: '32px',
            borderRadius: '50%',
            cursor: 'pointer',
            border: 'none',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            fontSize: '18px',
            backdropFilter: 'blur(4px)',
          }}>
          ×
        </button>
      </div>

      <div style={{ padding: '20px' }}>
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            marginBottom: '10px',
          }}>
          <span style={{ fontSize: '1.1rem', fontWeight: 'bold' }}>Road Conditions</span>
          <span
            style={{
              background: getRQIColor(displayScore),
              color: '#000',
              padding: '4px 12px',
              borderRadius: '20px',
              fontWeight: 'bold',
              fontSize: '0.85rem',
            }}>
            {getRQILabel(displayScore)}
          </span>
        </div>

        <div style={{ display: 'flex', alignItems: 'baseline', gap: '8px' }}>
          <span style={{ fontSize: '2.5rem', fontWeight: '800', lineHeight: 1 }}>
            {displayScore !== undefined ? displayScore.toFixed(1) : '-'}
          </span>
          <div style={{ display: 'flex', flexDirection: 'column' }}>
             <span style={{ color: 'var(--text-dim)', fontSize: '0.9rem' }}>/ 5.0 RQI Score</span>
             <span style={{ color: targetModel === 'dino' ? '#34d399' : '#60a5fa', fontSize: '0.7rem', fontWeight: 600, textTransform: 'uppercase' }}>
                {sourceLabel} AI
             </span>
          </div>
        </div>

        <div
          style={{
            marginTop: '15px',
            paddingTop: '15px',
            borderTop: '1px solid rgba(255,255,255,0.1)',
            fontSize: '0.9rem',
            color: 'var(--text-dim)',
          }}>
          Recorded:{' '}
          {detail.created_at ? new Date(detail.created_at).toLocaleDateString() : 'Unknown'}
          <button
            onClick={() => onTrain(detail.id, targetModel)}
            style={{
              marginTop: '10px',
              width: '100%',
              padding: '8px',
              background: 'rgba(255,255,255,0.1)',
              border: '1px solid rgba(255,255,255,0.2)',
              borderRadius: '8px',
              color: 'white',
              cursor: 'pointer',
              fontSize: '0.9rem',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              gap: '8px',
            }}>
            <span>✏️</span> Train / Correct
          </button>
        </div>
      </div>
    </div>
  )
}

export default PointDetailCard
