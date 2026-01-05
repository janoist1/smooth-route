import React, { useState, useEffect } from 'react'
import { useTraining } from '../../hooks'
import type { DamageLabel } from '../../types'
import Toolbar from '../Toolbar'
import { LoaderOverlay, StatusToast } from '../../../ui'
import { ImageNavigation } from './ImageNavigation'
import { BottomPanel } from './BottomPanel'
import { Canvas } from './Canvas'

interface TrainingViewProps {
  allIds: (string | number)[]
  onNext: (id: string | number) => void
  onPrev: (id: string | number) => void
  onClose: () => void
}

const TrainingView: React.FC<TrainingViewProps> = ({ allIds, onNext, onPrev, onClose }) => {
  const {
    imageId,
    imageUrl,
    loading,
    saving,
    error,
    annotations,
    selectedTool,
    manualRqi,
    tags,
    addAnnotation,
    updateAnnotation,
    setTool,
    saveAnnotations,
    deleteTrainingData,
    removeAnnotation,
    setRqi,
    addTag,
    removeTag,
    manualComment,
    setComment,
    setSettings,
    lastSavedSettings,
    autoDetect,
    autoDetectConf,
    setAutoDetectConf,
    autoDetectClasses,
    setAutoDetectClasses,
    filterCurrentAnnotations,
  } = useTraining()

  const [showSavedFeedback, setShowSavedFeedback] = useState(false)
  const [imageLoaded, setImageLoaded] = useState(false)
  const [lastImageUrl, setLastImageUrl] = useState<string | null>(null)
  const [selectedAnnotationId, setSelectedAnnotationId] = useState<string | null>(null)
  const [filterThreshold, setFilterThreshold] = useState(0.3)

  // Handle tool change: if in edit mode with selected annotation, change its label
  const handleToolChange = React.useCallback(
    (tool: DamageLabel) => {
      if (selectedTool === 'edit' && selectedAnnotationId && tool !== 'edit') {
        // Change the label of the selected annotation
        const annotation = annotations.find(a => a.id === selectedAnnotationId)
        if (annotation) {
          updateAnnotation({
            ...annotation,
            label: tool,
          })
          // Stay in edit mode to continue editing
          return
        }
      }
      // Normal tool switch
      setTool(tool)
    },
    [selectedTool, selectedAnnotationId, annotations, updateAnnotation, setTool],
  )


  // Reset image loaded state when URL changes
  if (imageUrl !== lastImageUrl) {
    setLastImageUrl(imageUrl)
    setImageLoaded(false)
  }

  // Navigation Logic
  const currentIndex = allIds.findIndex(id => String(id) === String(imageId))
  const hasNext = currentIndex !== -1 && currentIndex < allIds.length - 1
  const hasPrev = currentIndex > 0

  const handleNext = React.useCallback(() => {
    if (hasNext) {
      const nextId = allIds[currentIndex + 1]
      onNext(nextId)
    }
  }, [hasNext, allIds, currentIndex, onNext])

  const handlePrev = React.useCallback(() => {
    if (hasPrev) {
      const prevId = allIds[currentIndex - 1]
      onPrev(prevId)
    }
  }, [hasPrev, allIds, currentIndex, onPrev])

  const handleDelete = React.useCallback(() => {
    if (!imageUrl) return
    const parts = imageUrl.split('/')
    const filename = parts[parts.length - 1]

    if (
      window.confirm(
        'Biztosan törölni akarod ezt a tanítási adatot? (Csak a te jelöléseid törlődnek, a kép megmarad)',
      )
    ) {
      deleteTrainingData(filename)
      if (hasNext) handleNext()
      else onClose()
    }
  }, [imageUrl, deleteTrainingData, hasNext, handleNext, onClose])

  const handleSave = React.useCallback(() => {
    setShowSavedFeedback(false)
    saveAnnotations()
    if (!saving) {
      setShowSavedFeedback(true)
      setTimeout(() => setShowSavedFeedback(false), 2000)
    }
  }, [saveAnnotations, saving])

  const handleApplyPrevious = React.useCallback(() => {
    if (lastSavedSettings) {
      setSettings(lastSavedSettings)
    }
  }, [lastSavedSettings, setSettings])

  // Global Keyboard Shortcuts (Tools)
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) return

      switch (e.key.toLowerCase()) {
        case 'arrowleft':
          handlePrev()
          break
        case 'arrowright':
          handleNext()
          break
        case 'w':
          autoDetect(autoDetectConf)
          break
        case 'f':
          filterCurrentAnnotations(filterThreshold)
          break
        case 'l':
          handleToolChange('long_crack')
          break
        case 't':
          handleToolChange('trans_crack')
          break
        case 'a':
          handleToolChange('alligator_crack')
          break
        case 'p':
          handleToolChange('pothole')
          break
        case 'b':
          handleToolChange('patch')
          break
        case 'd':
          handleToolChange('degradation')
          break
        case 's':
          handleToolChange('shadow')
          break
        case 'm':
          handleToolChange('manhole')
          break
        case 'k':
          handleToolChange('marking')
          break
        case 'v':
          handleToolChange('ignore')
          break
        case 'e':
          setTool('edit')
          break
        case 'escape':
          // Canvas handles ESC for drawing abort. Parent handles it for Close?
          // Since we captured ESC in Canvas with stopPropagation, this will only fire if NOT drawing.
          onClose()
          break
        case ' ':
          e.preventDefault()
          handleApplyPrevious()
          break
        case 'enter':
          // Canvas handling?
          if (!e.defaultPrevented) {
            e.preventDefault()
            handleSave()
            if (hasNext) handleNext()
          }
          break
      }
    }

    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [
    handleToolChange,
    handleSave,
    handlePrev,
    handleNext,
    onClose,
    handleApplyPrevious,
    hasNext,
    setTool,
    autoDetect,
    autoDetectConf,
    filterCurrentAnnotations,
    filterThreshold,
  ])

  // Show overlay ONLY if we are loading AND don't have an image yet
  // This prevents the overlay from showing during background detection
  const isGlobalLoading = (loading && !imageUrl) || !imageLoaded

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
      {isGlobalLoading && <LoaderOverlay />}

      <Toolbar
        selectedTool={selectedTool}
        setTool={handleToolChange}
        onSave={handleSave}
        onDelete={handleDelete}
        onApplyPrevious={lastSavedSettings ? handleApplyPrevious : undefined}
        onAutoDetect={() => autoDetect(autoDetectConf)}
        autoDetectConf={autoDetectConf}
        onConfChange={setAutoDetectConf}
        autoDetectClasses={autoDetectClasses}
        onClassesChange={setAutoDetectClasses}
        loading={loading}
        // Filter Tool Wiring
        onFilter={(threshold) => filterCurrentAnnotations(threshold)}
        filterThreshold={filterThreshold}
        onFilterThreshChange={setFilterThreshold}
      />

      <div
        style={{
          flex: 1,
          display: 'flex',
          overflow: 'hidden',
          marginLeft: '60px',
          width: 'calc(100vw - 60px)',
          position: 'relative',
        }}>
        <StatusToast saving={saving} showSavedFeedback={showSavedFeedback} />

        {/* Canvas & Navigation */}
        <Canvas
          imageUrl={imageUrl || ''}
          annotations={annotations}
          selectedTool={selectedTool}
          addAnnotation={addAnnotation}
          removeAnnotation={removeAnnotation}
          updateAnnotation={updateAnnotation}
          onImageLoad={() => setImageLoaded(true)}
          onAnnotationSelect={setSelectedAnnotationId}
        />

        <ImageNavigation
          hasPrev={hasPrev}
          hasNext={hasNext}
          onPrev={handlePrev}
          onNext={handleNext}
          onClose={onClose}
        />
      </div>

      <BottomPanel
        manualRqi={manualRqi}
        setRqi={setRqi}
        annotations={annotations}
        tags={tags}
        addTag={addTag}
        removeTag={removeTag}
        manualComment={manualComment}
        setComment={setComment}
      />
    </div>
  )
}

export default TrainingView
