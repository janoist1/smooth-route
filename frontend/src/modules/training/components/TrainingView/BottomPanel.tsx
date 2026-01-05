import React, { useState } from 'react'
import type { Annotation } from '../../types'

interface BottomPanelProps {
  manualRqi: number | null
  setRqi: (val: number) => void
  annotations: Annotation[]
  tags: string[]
  addTag: (tag: string) => void
  removeTag: (tag: string) => void
  manualComment: string
  setComment: (val: string) => void
}

const getColorForRqi = (score: number) => {
  if (score <= 2.0) return '#22c55e'
  if (score <= 3.5) return '#facc15'
  return '#ef4444'
}

export const BottomPanel: React.FC<BottomPanelProps> = ({
  manualRqi,
  setRqi,
  annotations,
  tags,
  addTag,
  removeTag,
  manualComment,
  setComment,
}) => {
  const [tagInput, setTagInput] = useState('')

  const handleTagKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && tagInput.trim()) {
      addTag(tagInput.trim())
      setTagInput('')
    }
  }

  // Calculate polygon coverage % (simplified)
  const polygonCount = annotations.filter(
    a => a.type === 'polygon' && !['shadow', 'manhole', 'marking'].includes(a.label),
  ).length
  const coveragePercent = polygonCount > 0 ? '~' + (polygonCount * 1.5).toFixed(1) + '%' : '0.0%'

  return (
    <div
      style={{
        height: '220px',
        background: '#1e1e1e',
        borderTop: '1px solid #333',
        display: 'flex',
        fontSize: '13px',
        color: '#ccc',
        marginLeft: '60px',
      }}>
      {/* Column 1: RQI (Left) */}
      <div
        style={{
          width: '280px',
          padding: '15px',
          borderRight: '1px solid #333',
          display: 'flex',
          flexDirection: 'column',
          justifyContent: 'center',
          gap: '8px',
        }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <span style={{ fontWeight: 600 }}>Ground Truth RQI</span>
          <span
            style={{
              background: manualRqi ? getColorForRqi(manualRqi) : '#333',
              padding: '2px 8px',
              borderRadius: '4px',
              color: 'white',
              fontWeight: 'bold',
              fontSize: '14px',
            }}>
            {manualRqi ? manualRqi.toFixed(1) : '?.?'}
          </span>
        </div>

        <input
          type="range"
          min="1"
          max="5"
          step="0.5"
          value={manualRqi || 1}
          onChange={e => setRqi(parseFloat(e.target.value))}
          style={{ width: '100%', cursor: 'pointer', accentColor: '#3b82f6' }}
        />

        <div
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            fontSize: '10px',
            color: '#666',
            marginBottom: '10px',
          }}>
          <span>Excellent (1.0)</span>
          <span>Poor (5.0)</span>
        </div>

        <div
          style={{
            marginTop: '5px',
            padding: '8px',
            background: 'rgba(255,255,255,0.03)',
            borderRadius: '6px',
            border: '1px solid rgba(255,255,255,0.05)',
            fontSize: '11px',
          }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '4px' }}>
            <span style={{ color: '#888' }}>Kiszámított terület %:</span>
            <span style={{ color: '#aaa', fontWeight: 'bold' }}>{coveragePercent}</span>
          </div>
          <p style={{ margin: 0, fontSize: '9px', color: '#555', fontStyle: 'italic' }}>
            Az AI százalékot mér, de a tanításhoz a PASER (1-5) skála javasolt.
          </p>
        </div>
      </div>

      {/* Column 2: Tags (Middle) */}
      <div
        style={{
          flex: 1,
          padding: '15px',
          display: 'flex',
          flexDirection: 'column',
          gap: '8px',
          minWidth: 0,
        }}>
        <span style={{ fontSize: '13px', color: '#ccc', marginBottom: '4px' }}>Tags</span>

        <div
          style={{
            display: 'flex',
            flexDirection: 'column',
            gap: '12px',
            flex: 1,
            overflowY: 'auto',
            paddingRight: '5px',
          }}>
          {/* Group 1: Surface & Condition */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
            <span
              style={{
                fontSize: '10px',
                textTransform: 'uppercase',
                color: '#666',
                fontWeight: 'bold',
              }}>
              Surface Details
            </span>
            <div style={{ display: 'flex', gap: '6px', flexWrap: 'wrap' }}>
              {[
                'smooth',
                'uneven',
                'mild_wear',
                'heavy_wear',
                'fragmented',
                'cracked',
                'patched',
              ].map(tag => {
                const isActive = tags.includes(tag)
                return (
                  <button
                    key={tag}
                    onClick={() => (isActive ? removeTag(tag) : addTag(tag))}
                    style={{
                      background: isActive ? '#3b82f6' : '#2a2a2a',
                      border: isActive ? '1px solid #3b82f6' : '1px solid #444',
                      color: isActive ? 'white' : '#ccc',
                      padding: '3px 8px',
                      borderRadius: '4px',
                      cursor: 'pointer',
                      fontSize: '11px',
                      transition: 'all 0.1s',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                    }}>
                    {tag}
                  </button>
                )
              })}
            </div>
          </div>

          {/* Group 2: Environment */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
            <span
              style={{
                fontSize: '10px',
                textTransform: 'uppercase',
                color: '#666',
                fontWeight: 'bold',
              }}>
              Environment
            </span>
            <div style={{ display: 'flex', gap: '6px', flexWrap: 'wrap' }}>
              {['shadow', 'wet', 'glare', 'occlusion', 'blur', 'car', 'person'].map(tag => {
                const isActive = tags.includes(tag)
                return (
                  <button
                    key={tag}
                    onClick={() => (isActive ? removeTag(tag) : addTag(tag))}
                    style={{
                      background: isActive ? '#059669' : '#2a2a2a', // Green-ish for env
                      border: isActive ? '1px solid #059669' : '1px solid #444',
                      color: isActive ? 'white' : '#ccc',
                      padding: '3px 8px',
                      borderRadius: '4px',
                      cursor: 'pointer',
                      fontSize: '11px',
                      transition: 'all 0.1s',
                    }}>
                    {tag}
                  </button>
                )
              })}
            </div>
          </div>
        </div>

        {/* Custom Input */}
        <div style={{ marginTop: 'auto', borderTop: '1px solid #333', paddingTop: '8px' }}>
          <input
            type="text"
            value={tagInput}
            onChange={e => setTagInput(e.target.value)}
            onKeyDown={handleTagKeyDown}
            placeholder="+ Add helper tag..."
            style={{
              background: 'transparent',
              border: 'none',
              borderBottom: '1px solid #444',
              color: 'white',
              padding: '4px 0',
              outline: 'none',
              width: '100%',
              fontSize: '12px',
            }}
          />
        </div>
      </div>

      {/* Column 3: Comment (Right) */}
      <div
        style={{
          width: '300px',
          padding: '15px',
          borderLeft: '1px solid #333',
          display: 'flex',
          flexDirection: 'column',
          gap: '5px',
        }}>
        <span>Comment</span>
        <textarea
          value={manualComment}
          onChange={e => setComment(e.target.value)}
          placeholder="Additional notes about this image..."
          style={{
            flex: 1,
            background: '#222',
            border: '1px solid #444',
            color: 'white',
            padding: '8px',
            borderRadius: '4px',
            resize: 'none',
            fontSize: '12px',
            outline: 'none',
          }}
        />
      </div>
    </div>
  )
}
