import React, { useRef, useState, useEffect } from 'react'
import { useNavigate, useLocation } from 'react-router-dom'
import { useSelector } from 'react-redux'
import { useTraining } from '../hooks'
import type { AnnotationBox, TrainingState } from '../types'
import Toolbar from './Toolbar'
import { X, ChevronLeft, ChevronRight } from 'lucide-react'

interface TrainingLocationState {
  allIds?: (string | number)[]
}

interface TrainingViewProps {
  reviewMode?: boolean
}

const TrainingView: React.FC<TrainingViewProps> = ({ reviewMode }) => {
  const navigate = useNavigate()
  const location = useLocation()
  
  // Get navigation context from Redux (preferred) or Location State (fallback)
  const navIdsFromRedux = useSelector((state: { training: TrainingState }) => state.training.navigationIds)
  const allIds = React.useMemo(() => {
    if (navIdsFromRedux && navIdsFromRedux.length > 0) return navIdsFromRedux
    return (location.state as TrainingLocationState)?.allIds || []
  }, [navIdsFromRedux, location.state])
  const {
    imageId,
    imageUrl,
    loading,
    error,
    annotations,
    selectedTool,
    manualRqi,
    tags,
    addAnnotation,
    removeAnnotation,
    setTool,
    saveAnnotations,
    setRqi,
    addTag,
    removeTag,
    manualComment,
    setComment,
    setSettings,
    lastSavedSettings,
  } = useTraining()

  // Local state for tag input
  const [tagInput, setTagInput] = useState('')
  const [isDrawing, setIsDrawing] = useState(false)
  const [startPos, setStartPos] = useState({ x: 0, y: 0 })
  const [currentPos, setCurrentPos] = useState({ x: 0, y: 0 })
  const imageRef = useRef<HTMLImageElement>(null)
  const containerRef = useRef<HTMLDivElement>(null)

  const handleApplyPrevious = React.useCallback(() => {
    if (lastSavedSettings) {
      setSettings(lastSavedSettings)
    }
  }, [lastSavedSettings, setSettings])

  // Navigation Helpers
  const currentIndex = allIds.findIndex(id => String(id) === String(imageId))
  const hasNext = currentIndex !== -1 && currentIndex < allIds.length - 1
  const hasPrev = currentIndex > 0

  const handleNext = React.useCallback(() => {
    if (hasNext) {
      const nextId = allIds[currentIndex + 1]
      navigate(`/training/${nextId}/review`, { state: { allIds } })
    }
  }, [hasNext, allIds, currentIndex, navigate])

  const handlePrev = React.useCallback(() => {
    if (hasPrev) {
      const prevId = allIds[currentIndex - 1]
      navigate(`/training/${prevId}/review`, { state: { allIds } })
    }
  }, [hasPrev, allIds, currentIndex, navigate])

  // Keyboard Shortcuts
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      // Ignore if typing in input
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) return

      switch (e.key.toLowerCase()) {
        case 'arrowleft':
          handlePrev()
          break
        case 'arrowright':
          handleNext()
          break
        case 'p':
          setTool('pothole')
          break
        case 'a':
          setTool('patch')
          break
        case 's':
          setTool('shadow')
          break
        case 'c':
          setTool('cracks')
          break
        case ' ': // Space key
          e.preventDefault()
          handleApplyPrevious()
          break
        case 'enter':
          e.preventDefault()
          saveAnnotations()
          
          if (reviewMode) {
             handleNext()
          } else {
             // If not in review mode (e.g. single view), maybe just save? 
             // Logic kept simple: enter saves, and if listing exists, moves next.
             if (hasNext) handleNext()
          }
          break
      }
    }

    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [setTool, saveAnnotations, reviewMode, handleNext, handlePrev, handleApplyPrevious, hasNext])

  // Global mouse tracking / Clamping
  useEffect(() => {
    if (!isDrawing) return

    const handleWindowMouseMove = (e: MouseEvent) => {
      if (!imageRef.current || !startPos) return

      const rect = imageRef.current.getBoundingClientRect()
      // Clamp X and Y relative to image
      let x = e.clientX - rect.left
      let y = e.clientY - rect.top

      // Clamp to boundaries
      x = Math.max(0, Math.min(x, rect.width))
      y = Math.max(0, Math.min(y, rect.height))

      setCurrentPos({ x, y })
    }

    window.addEventListener('mousemove', handleWindowMouseMove)
    return () => {
      window.removeEventListener('mousemove', handleWindowMouseMove)
    }
  }, [isDrawing, startPos])

  // Handle Mouse Up Gloablly
  useEffect(() => {
    const handleWindowMouseUp = (e: MouseEvent) => {
      if (!isDrawing || !imageRef.current) return

      const rect = imageRef.current.getBoundingClientRect()
      let endX = e.clientX - rect.left
      let endY = e.clientY - rect.top

      // Clamp for final logic
      endX = Math.max(0, Math.min(endX, rect.width))
      endY = Math.max(0, Math.min(endY, rect.height))

      const w = Math.abs(endX - startPos.x)
      const h = Math.abs(endY - startPos.y)
      const x = Math.min(startPos.x, endX)
      const y = Math.min(startPos.y, endY)

      if (w > 5 && h > 5) {
        const newBox: AnnotationBox = {
          id: Date.now().toString(),
          x,
          y,
          w,
          h,
          label: selectedTool,
        }
        addAnnotation(newBox)
      }
      setIsDrawing(false)
    }

    if (isDrawing) {
      window.addEventListener('mouseup', handleWindowMouseUp)
    }
    return () => {
      window.removeEventListener('mouseup', handleWindowMouseUp)
    }
  }, [isDrawing, startPos, selectedTool, addAnnotation])

  const handleMouseDown = (e: React.MouseEvent) => {
    if (!imageRef.current || !containerRef.current) return
    const rect = imageRef.current.getBoundingClientRect()
    const x = e.clientX - rect.left
    const y = e.clientY - rect.top
    setIsDrawing(true)
    setStartPos({ x, y })
    setCurrentPos({ x, y })
  }

  // Helper to render temp box
  const getCurrentBox = () => {
    if (!isDrawing) return null
    const w = Math.abs(currentPos.x - startPos.x)
    const h = Math.abs(currentPos.y - startPos.y)
    const left = Math.min(startPos.x, currentPos.x)
    const top = Math.min(startPos.y, currentPos.y)
    return { left, top, w, h }
  }

  // Helper for adding tag on Enter
  const handleTagKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && tagInput.trim()) {
      addTag(tagInput.trim())
      setTagInput('')
    }
  }

  const [imageLoaded, setImageLoaded] = useState(false)
  const [lastImageUrl, setLastImageUrl] = useState<string | null>(null)

  // Reset image loaded state when URL changes (Render-cycle state derivation)
  if (imageUrl !== lastImageUrl) {
    setLastImageUrl(imageUrl)
    setImageLoaded(false)
  }

  const handleImageLoad = () => {
    setImageLoaded(true)
  }

  // Combined loading state
  // We consider it loading if:
  // 1. Redux is fetching
  // 2. We have no image URL yet (and no error)
  // 3. The specific image hasn't finished loading in the DOM
  const isGlobalLoading = loading || !imageUrl || !imageLoaded

  if (error)
    return (
      <div className="flex items-center justify-center h-screen text-red-500">Error: {error}</div>
    )

  return (
    <div
      style={{
        height: '100vh',
        width: '100vw',
        background: '#222',
        display: 'flex',
        flexDirection: 'column',
        position: 'relative',
      }}>
      {/* Global Loader Overlay */}
      {isGlobalLoading && (
        <div
          style={{
            position: 'absolute',
            inset: 0,
            zIndex: 50,
            background: '#111',
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            justifyContent: 'center',
            color: 'white',
          }}>
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-500 mb-4"></div>
          <div className="text-lg font-medium">Loading Training Data...</div>
        </div>
      )}

      <div style={{ flex: 1, display: 'flex', overflow: 'hidden' }}>
        {/* Photoshop-style Toolbar */}
        <Toolbar 
          selectedTool={selectedTool} 
          setTool={setTool} 
          onSave={saveAnnotations} 
          onApplyPrevious={lastSavedSettings ? handleApplyPrevious : undefined}
        />
        
        {/* Canvas Area representation... (removed old float button) */}
        <div
          ref={containerRef}
          style={{
            flex: 1,
            display: 'flex',
            justifyContent: 'center',
            alignItems: 'center',
            position: 'relative',
            overflow: 'hidden',
            background: '#333',
          }}>
          {/* Close / Back Button */}
          <button
            onClick={() => navigate(reviewMode ? '/training' : '/')}
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

          {imageUrl && (
            <div style={{ position: 'relative', boxShadow: '0 0 20px rgba(0,0,0,0.5)' }}>
              <img
                ref={imageRef}
                src={imageUrl}
                alt="Training"
                draggable={false}
                onLoad={handleImageLoad}
                onMouseDown={handleMouseDown}
                style={{
                  maxWidth: '100%',
                  maxHeight: '80vh',
                  display: 'block',
                  cursor: 'crosshair',
                }}
              />
              {/* Render Boxes */}
              {annotations.map(box => (
                <div
                  key={box.id}
                  style={{
                    position: 'absolute',
                    left: box.x,
                    top: box.y,
                    width: box.w,
                    height: box.h,
                    border: `2px solid ${getColorForLabel(box.label)}`,
                    background: `rgba(${getRgbForLabel(box.label)}, 0.2)`,
                    pointerEvents: 'auto', // Enable pointer events for interaction
                    cursor: 'context-menu',
                  }}
                  onContextMenu={e => {
                    e.preventDefault()
                    e.stopPropagation() // Prevent event bubbling to avoid conflicts
                    removeAnnotation(box.id)
                  }}>
                  <span
                    style={{
                      position: 'absolute',
                      top: -20,
                      left: 0,
                      background: getColorForLabel(box.label),
                      color: 'white',
                      padding: '2px 4px',
                      fontSize: '10px',
                    }}>
                    {box.label}
                  </span>
                </div>
              ))}

              {/* Render Ghost Box while drawing */}
              {isDrawing &&
                (() => {
                  const ghost = getCurrentBox()
                  if (!ghost) return null
                  return (
                    <div
                      style={{
                        position: 'absolute',
                        left: ghost.left,
                        top: ghost.top,
                        width: ghost.w,
                        height: ghost.h,
                        border: `2px dashed ${getColorForLabel(selectedTool)}`,
                        background: `rgba(${getRgbForLabel(selectedTool)}, 0.1)`,
                        pointerEvents: 'none',
                      }}
                    />
                  )
                })()}
            </div>
          )}
        </div>

        {/* Navigation Arrows (Floating) */}
        {hasPrev && (
          <button
            onClick={handlePrev}
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
            onMouseOut={e => (e.currentTarget.style.background = 'rgba(0,0,0,0.5)')}
          >
            <ChevronLeft size={32} />
          </button>
        )}
        
        {hasNext && (
          <button
            onClick={handleNext}
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
            onMouseOut={e => (e.currentTarget.style.background = 'rgba(0,0,0,0.5)')}
          >
            <ChevronRight size={32} />
          </button>
        )}
      </div>

      {/* Bottom Panel: RQI & Tags */}
      {/* Bottom Panel: RQI & Tags */}
      <div
        style={{
          height: '220px',
          background: '#1e1e1e',
          borderTop: '1px solid #333',
          display: 'flex',
          fontSize: '13px',
          color: '#ccc',
        }}>
        {/* Column 1: RQI (Left) */}
        <div
          style={{
            width: '250px',
            padding: '15px',
            borderRight: '1px solid #333',
            display: 'flex',
            flexDirection: 'column',
            justifyContent: 'center',
            gap: '10px',
          }}>
          <div style={{ display: 'flex', justifyContent: 'space-between' }}>
            <span>Manual RQI</span>
            <span
              style={{ fontWeight: 'bold', color: manualRqi ? getColorForRqi(manualRqi) : '#666' }}>
              {manualRqi ? manualRqi.toFixed(1) : 'Not Rated'}
            </span>
          </div>
          <input
            type="range"
            min="1"
            max="5"
            step="0.5"
            value={manualRqi || 1}
            onChange={e => setRqi(parseFloat(e.target.value))}
            style={{ width: '100%', cursor: 'pointer' }}
          />
          <div
            style={{
              display: 'flex',
              justifyContent: 'space-between',
              fontSize: '10px',
              color: '#666',
            }}>
            <span>Excellent (1.0)</span>
            <span>Poor (5.0)</span>
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
    </div>
  )
}

// Helpers (Keep colors same for consistency)
const getColorForRqi = (score: number) => {
  // Backend Logic: 1.0 (No Damage) -> 5.0 (Severe Damage)
  if (score <= 2.0) return '#22c55e' // Green (Good)
  if (score <= 3.5) return '#facc15' // Yellow (Medium)
  return '#ef4444' // Red (Bad)
}

const getColorForLabel = (label: string) => {
  switch (label) {
    case 'pothole':
      return '#ef4444'
    case 'patch':
      return '#facc15'
    case 'shadow':
      return '#3b82f6'
    case 'cracks':
      return '#a855f7'
    default:
      return '#fff'
  }
}

const getRgbForLabel = (label: string) => {
  switch (label) {
    case 'pothole':
      return '239, 68, 68'
    case 'patch':
      return '250, 204, 21'
    case 'shadow':
      return '59, 130, 246'
    case 'cracks':
      return '168, 85, 247'
    default:
      return '255, 255, 255'
  }
}

export default TrainingView
