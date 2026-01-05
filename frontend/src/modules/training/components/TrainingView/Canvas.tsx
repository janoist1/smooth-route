import React, { useRef, useState, useEffect } from 'react'
import type { Annotation, DamageLabel } from '../../types' // Type-only import
import { getColorForLabel, getRgbForLabel } from './colors'

interface CanvasProps {
  imageUrl: string
  annotations: Annotation[]
  selectedTool: string
  addAnnotation: (ann: Annotation) => void
  removeAnnotation: (id: string) => void
  updateAnnotation: (ann: Annotation) => void
  onImageLoad: () => void
  onAnnotationSelect?: (id: string | null) => void
}

export const Canvas: React.FC<CanvasProps> = ({
  imageUrl,
  annotations,
  selectedTool,
  addAnnotation,
  removeAnnotation,
  updateAnnotation,
  onImageLoad,
  onAnnotationSelect,
}) => {
  const [currentPoints, setCurrentPoints] = useState<[number, number][]>([])
  const [selectedAnnotationId, setSelectedAnnotationId] = useState<string | null>(null)
  const [editingPoints, setEditingPoints] = useState<[number, number][] | null>(null)
  const [originalPoints, setOriginalPoints] = useState<[number, number][] | null>(null)
  const [draggingPointIndex, setDraggingPointIndex] = useState<number | null>(null)
  const imageRef = useRef<HTMLImageElement>(null)
  const containerRef = useRef<HTMLDivElement>(null)

  const finishPolygon = React.useCallback(() => {
    if (currentPoints.length < 3) return

    const newPoly: Annotation = {
      id: Date.now().toString(),
      type: 'polygon',
      label: selectedTool as DamageLabel, // Cast string to DamageLabel
      points: currentPoints,
    }
    addAnnotation(newPoly)
    setCurrentPoints([])
  }, [currentPoints, selectedTool, addAnnotation])

  // Handle polygon selection in Edit mode
  const handlePolygonClick = (annotationId: string) => {
    if (selectedTool !== 'edit') return
    const annotation = annotations.find(a => a.id === annotationId)
    if (annotation && annotation.points) {
      setSelectedAnnotationId(annotationId)
      setEditingPoints([...annotation.points])
      setOriginalPoints([...annotation.points]) // Store original points for revert
      onAnnotationSelect?.(annotationId)
    }
  }
  
  // Handle polygon deletion (right-click on body)
  const handlePolygonRightClick = (e: React.MouseEvent, annotationId: string) => {
    e.preventDefault()
    e.stopPropagation()
    removeAnnotation(annotationId)
    if (selectedAnnotationId === annotationId) {
      setSelectedAnnotationId(null)
      setEditingPoints(null)
      onAnnotationSelect?.(null)
    }
  }

  // Handle point dragging
  const handlePointMouseDown = (e: React.MouseEvent, pointIndex: number) => {
    if (selectedTool !== 'edit' || !editingPoints) return
    e.stopPropagation()
    setDraggingPointIndex(pointIndex)
  }

  const handlePointMouseMove = (e: React.MouseEvent) => {
    if (draggingPointIndex === null || !editingPoints || !imageRef.current) return
    
    const rect = imageRef.current.getBoundingClientRect()
    const x = Math.round(e.clientX - rect.left)
    const y = Math.round(e.clientY - rect.top)
    
    const newPoints = [...editingPoints]
    newPoints[draggingPointIndex] = [x, y]
    setEditingPoints(newPoints)
  }

  const handlePointMouseUp = () => {
    if (draggingPointIndex !== null && editingPoints && selectedAnnotationId) {
      // Save the edited polygon
      const annotation = annotations.find(a => a.id === selectedAnnotationId)
      if (annotation) {
        updateAnnotation({
          ...annotation,
          points: editingPoints,
        })
      }
    }
    setDraggingPointIndex(null)
  }

  // Handle point deletion (right-click)
  const handlePointRightClick = (e: React.MouseEvent, pointIndex: number) => {
    e.preventDefault()
    e.stopPropagation()
    if (!editingPoints || editingPoints.length <= 3) return // Minimum 3 points for polygon
    
    const newPoints = editingPoints.filter((_, i) => i !== pointIndex)
    setEditingPoints(newPoints)
    
    if (selectedAnnotationId) {
      const annotation = annotations.find(a => a.id === selectedAnnotationId)
      if (annotation) {
        updateAnnotation({
          ...annotation,
          points: newPoints,
        })
      }
    }
  }

  const handleMouseDown = (e: React.MouseEvent) => {
    if (selectedTool === 'edit') return // Don't draw in edit mode
    
    if (!imageRef.current) return
    const rect = imageRef.current.getBoundingClientRect()
    const x = e.clientX - rect.left
    const y = e.clientY - rect.top

    // Add point to current polygon
    setCurrentPoints([...currentPoints, [Math.round(x), Math.round(y)]])
  }

  const handleDoubleClick = (e: React.MouseEvent) => {
    if (selectedTool === 'edit') return // No double-click behavior in edit mode
    
    e.preventDefault()
    finishPolygon()
  }

  // Clear selection when switching away from edit mode
  useEffect(() => {
    if (selectedTool !== 'edit') {
      // Schedule state updates to avoid cascading renders
      const timer = setTimeout(() => {
        setSelectedAnnotationId(null)
        setEditingPoints(null)
        setOriginalPoints(null)
        setDraggingPointIndex(null)
        onAnnotationSelect?.(null)
      }, 0)
      return () => clearTimeout(timer)
    }
  }, [selectedTool, onAnnotationSelect])

  // Keyboard support for finishing/canceling *viewport* specifically not global?
  // Actually the global keyboard listener in index.tsx handles tool switching.
  // But local ESC/Enter for drawing is handled here IF we want to encapsulate.
  // The original code had ONE big useEffect for keys.
  // It's better if the parent handles keys, OR we move drawing-specific keys here.
  // BUT the parent needs to know `currentPoints.length` to decide if `Escape` means "Clear points" or "Go Back".
  // So exposing `currentPoints` or moving the key handler here is tricky.
  // Simplest: exposing `currentPoints` state to parent is Anti-pattern.
  // Better: Parent manages `currentPoints`? Or Parent delegates events?
  // Let's keep `currentPoints` local to Canvas, but listen to global window events inside Canvas for ESC/Enter *only when drawing*.

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      // Only care if drawing or saving
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) return

      if (e.key === 'Escape') {
        if (selectedTool === 'edit' && selectedAnnotationId && originalPoints) {
          e.preventDefault()
          e.stopPropagation()
          // Revert changes
          const annotation = annotations.find(a => a.id === selectedAnnotationId)
          if (annotation) {
             updateAnnotation({
               ...annotation,
               points: originalPoints,
             })
          }
          // Clear selection
          setSelectedAnnotationId(null)
          setEditingPoints(null)
          setOriginalPoints(null)
          setDraggingPointIndex(null)
          onAnnotationSelect?.(null)
          return
        }

        if (currentPoints.length > 0) {
          setCurrentPoints([])
          e.stopPropagation() // Prevent parent from handling Back
        }
      } else if (e.key === 'Enter') {
        if (selectedTool === 'edit' && selectedAnnotationId) {
          e.preventDefault()
          e.stopPropagation()
          setSelectedAnnotationId(null)
          setEditingPoints(null)
          setDraggingPointIndex(null)
          onAnnotationSelect?.(null)
          return
        }

        if (currentPoints.length >= 3) {
          e.preventDefault()
          finishPolygon()
        }
      }
    }
    window.addEventListener('keydown', handleKeyDown, { capture: true }) // Capture to handle before parent
    return () => window.removeEventListener('keydown', handleKeyDown, { capture: true })
  }, [
    currentPoints,
    finishPolygon,
    selectedTool,
    selectedAnnotationId,
    onAnnotationSelect,
    annotations,
    originalPoints,
    updateAnnotation,
  ])

  return (
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
      {/* Drawing Hint */}
      {currentPoints.length > 0 && (
        <div
          style={{
            position: 'absolute',
            top: '20px',
            left: '50%',
            transform: 'translateX(-50%)',
            zIndex: 100,
            background: 'rgba(59, 130, 246, 0.9)',
            color: 'white',
            padding: '8px 16px',
            borderRadius: '20px',
            fontSize: '13px',
            fontWeight: 600,
            boxShadow: '0 4px 12px rgba(0,0,0,0.3)',
            display: 'flex',
            alignItems: 'center',
            gap: '12px',
          }}>
          <span>Kijelölés folyamatban ({currentPoints.length} pont)</span>
          <div style={{ width: '1px', height: '15px', background: 'rgba(255,255,255,0.3)' }} />
          <span>
            <b>Dupla kattintás</b> vagy <b>Enter</b> a befejezéshez
          </span>
          <div style={{ width: '1px', height: '15px', background: 'rgba(255,255,255,0.3)' }} />
          <span>
            <b>Escape</b> az elvetéshez
          </span>
        </div>
      )}

      {imageUrl && (
        <div
          style={{
            position: 'relative',
            boxShadow: '0 0 20px rgba(0,0,0,0.5)',
            display: 'inline-block', // Match image size exactly
            lineHeight: 0, // Remove potential whitespace below image
          }}
          onContextMenu={e => {
            e.preventDefault()
            e.stopPropagation()
            
            // If in edit mode, let the specific polygon handlers handle it (if enabled)
            // But if we clicked 'outside' a polygon in edit mode, maybe we want to deselect?
            // Actually, if selectedTool !== 'edit', pointerEvents is 'none' on polygons,
            // so THIS handler receives the Right Click. We must manually check for collision.
            
            if (selectedTool !== 'edit' && imageRef.current) {
               const rect = imageRef.current.getBoundingClientRect()
               const x = e.clientX - rect.left
               const y = e.clientY - rect.top
               
               // Find top-most polygon under cursor (reverse order)
               // Ray-casting algorithm
               const isPointInPoly = (px: number, py: number, poly: number[][]) => {
                 let inside = false
                 for (let i = 0, j = poly.length - 1; i < poly.length; j = i++) {
                   const xi = poly[i][0], yi = poly[i][1]
                   const xj = poly[j][0], yj = poly[j][1]
                   const intersect = ((yi > py) !== (yj > py)) &&
                                     (px < (xj - xi) * (py - yi) / (yj - yi) + xi)
                   if (intersect) inside = !inside
                 }
                 return inside
               }
               
               // Check efficiently from top (latest) to bottom
               // Annotations are rendered in order, so last is on top.
               for (let i = annotations.length - 1; i >= 0; i--) {
                 const ann = annotations[i]
                 if (ann.type === 'polygon' && ann.points && isPointInPoly(x, y, ann.points)) {
                   removeAnnotation(ann.id)
                   return // Only delete one at a time (the top one)
                 }
               }
            }
          }}
          onMouseMove={handlePointMouseMove}
          onMouseUp={handlePointMouseUp}>
          <img
            ref={imageRef}
            src={imageUrl}
            alt="Training"
            draggable={false}
            onLoad={onImageLoad}
            onMouseDown={handleMouseDown}
            onDoubleClick={handleDoubleClick}
            style={{
              maxWidth: '100%',
              maxHeight: '80vh',
              display: 'block',
              cursor: 'crosshair',
            }}
          />

          {/* SVG Overlay for Polygons */}
          <svg
            style={{
              position: 'absolute',
              top: 0,
              left: 0,
              width: '100%',
              height: '100%',
              pointerEvents: 'none',
              zIndex: 10,
            }}>
            {/* Existing Annotations */}
            {annotations.map(ann => {
              if (ann.type === 'polygon' && ann.points) {
                const pointsStr = ann.points.map(p => `${p[0]},${p[1]}`).join(' ')
                const isEditing = ann.id === selectedAnnotationId && editingPoints !== null
                
                // Don't render if being edited
                if (isEditing) return null
                
                return (
                  <g key={ann.id}>
                    <polygon
                      points={pointsStr}
                      style={{
                        fill: `rgba(${getRgbForLabel(ann.label)}, 0.2)`,
                        stroke: getColorForLabel(ann.label),
                        strokeWidth: 2,
                        pointerEvents: selectedTool === 'edit' ? 'auto' : 'none',
                        cursor: selectedTool === 'edit' ? 'pointer' : 'default',
                      }}
                      onClick={() => handlePolygonClick(ann.id)}
                      onContextMenu={(e) => handlePolygonRightClick(e, ann.id)}
                    />
                    {/* Label tag */}
                    <text
                      x={ann.points[0][0]}
                      y={ann.points[0][1] - 5}
                      style={{
                        fill: 'white',
                        fontSize: '10px',
                        fontWeight: 'bold',
                        filter: 'drop-shadow(0 1px 1px black)',
                        pointerEvents: 'none',
                      }}>
                      {ann.label}
                    </text>
                  </g>
                )
              }
              return null
            })}

            {/* Editing Polygon */}
            {editingPoints && selectedAnnotationId && (() => {
              const annotation = annotations.find(a => a.id === selectedAnnotationId)
              const pointsStr = editingPoints.map(p => `${p[0]},${p[1]}`).join(' ')
              return (
                <g>
                  <polygon
                    points={pointsStr}
                    style={{
                      fill: `rgba(${getRgbForLabel(annotation?.label || 'long_crack')}, 0.3)`,
                      stroke: '#3b82f6',
                      strokeWidth: 3,
                      pointerEvents: 'none',
                    }}
                  />
                  {editingPoints.map((p, i) => (
                    <circle
                      key={i}
                      cx={p[0]}
                      cy={p[1]}
                      r={6}
                      style={{
                        fill: '#3b82f6',
                        stroke: 'white',
                        strokeWidth: 2,
                        cursor: 'move',
                        pointerEvents: 'auto',
                      }}
                      onMouseDown={(e) => handlePointMouseDown(e, i)}
                      onContextMenu={(e) => handlePointRightClick(e, i)}
                    />
                  ))}
                </g>
              )
            })()}

            {/* Current Drawing Polygon */}
            {currentPoints.length > 0 && (
              <g>
                <polyline
                  points={currentPoints.map(p => `${p[0]},${p[1]}`).join(' ')}
                  style={{
                    fill: 'none',
                    stroke: getColorForLabel(selectedTool),
                    strokeWidth: 2,
                    strokeDasharray: '4,2',
                  }}
                />
                {currentPoints.map((p, i) => (
                  <circle
                    key={i}
                    cx={p[0]}
                    cy={p[1]}
                    r={3}
                    style={{ fill: getColorForLabel(selectedTool) }}
                  />
                ))}
                {/* Closing line hint */}
                {currentPoints.length >= 3 && (
                  <line
                    x1={currentPoints[currentPoints.length - 1][0]}
                    y1={currentPoints[currentPoints.length - 1][1]}
                    x2={currentPoints[0][0]}
                    y2={currentPoints[0][1]}
                    style={{
                      stroke: getColorForLabel(selectedTool),
                      strokeWidth: 1,
                      strokeDasharray: '2,2',
                      opacity: 0.5,
                    }}
                  />
                )}
              </g>
            )}
          </svg>
        </div>
      )}
    </div>
  )
}
