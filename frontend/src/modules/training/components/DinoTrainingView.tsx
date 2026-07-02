import React, { useEffect, useCallback } from 'react'
import { useParams } from 'react-router-dom'
import { LoaderOverlay } from '../../ui'
import { useTraining } from '../hooks'

interface Props {
  onNext?: (id: string | number) => void
  onPrev?: (id: string | number) => void
  onClose?: () => void
}

// ... imports ...

export const DinoTrainingView: React.FC<Props> = ({ onNext, onPrev, onClose }) => {
  const { id } = useParams<{ id: string }>()
  const {
    imageUrl,
    loading,
    saving,
    error,
    manualRqi,
    items,
    previewUrl,
    loadingAction,
    // bound actions from the module hook (never import slice directly in a component)
    clearPreview,
    performReviewAction,
    saveDinoRqi,
    setRqi: setRqiAction,
    predictDinoRqi,
  } = useTraining()

  const [fastMode, setFastMode] = React.useState(false)
  const [preprocessingOptions, setPreprocessingOptions] = React.useState({
      useRoi: false,
      smartRoi: true, // Default to true as it is the primary method
      useMask: false,
      removeShadows1: false,
      removeShadows2: false
  })

  // Clear preview when reviewing a new image (remounted via key)
  useEffect(() => {
      clearPreview()
  }, [clearPreview])


  const toggleOption = (key: keyof typeof preprocessingOptions) => {
      const newOpts = { ...preprocessingOptions, [key]: !preprocessingOptions[key] }
      
      // Mutually exclusive ROI options? Maybe. Let's allow strictly one for UX if desired,
      // but backend can handle both (intersection).
      // Let's keep them independent for now.
      
      setPreprocessingOptions(newOpts)
      
      if (!newOpts.useRoi && !newOpts.smartRoi && !newOpts.useMask && !newOpts.removeShadows1 && !newOpts.removeShadows2) {
          clearPreview()
      } else {
          performReviewAction({
              actionType: 'preview_preprocessing',
              params: {
                  filename: imageUrl?.split('/').pop(),
                  options: {
                      use_roi: newOpts.useRoi,
                      smart_roi: newOpts.smartRoi,
                      use_mask: newOpts.useMask,
                      remove_shadows_1: newOpts.removeShadows1,
                      remove_shadows_2: newOpts.removeShadows2
                  }
              }
          })
      }
  }

  // Fetch is handled by router.ts saga

  const currentIndex = items.findIndex(item => String(item.id) === String(id))
  const nextId = currentIndex !== -1 && currentIndex < items.length - 1 ? items[currentIndex + 1].id : null
  const prevId = currentIndex > 0 ? items[currentIndex - 1].id : null

  // ... (handleSave, setRqi, handleKeyDown kept same) ...
  const handleSave = useCallback(async () => {
    try {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const result: any = await saveDinoRqi()

      // Normalize result (handle if it's the action object or the payload directly)
      const nextId = result?.nextId || result?.payload?.nextId

      // Navigate to server-provided next ID if available
      if (nextId) {
         if (onNext) onNext(nextId)
      } else {
         // Fallback or finish
         if (onClose) onClose()
      }
    } catch (error) {
      console.error("Save failed:", error)
    }
  }, [saveDinoRqi, onNext, onClose])

  const setRqi = useCallback((rqi: number) => {
    setRqiAction(rqi)
    if (fastMode) {
      setTimeout(() => handleSave(), 200)
    }
  }, [setRqiAction, fastMode, handleSave])

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) return

      if (e.key >= '1' && e.key <= '5') {
        setRqi(parseInt(e.key, 10))
      } else if (e.key === 'Enter') {
        if (!fastMode) handleSave()
      } else if (e.key === 'Escape') {
        if (onClose) onClose()
      } else if (e.key === 'ArrowLeft') {
        if (prevId && onPrev) onPrev(prevId)
      } else if (e.key === 'ArrowRight') {
        if (nextId && onNext) onNext(nextId)
      }
    }

    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [setRqi, handleSave, onClose, onNext, onPrev, nextId, prevId, fastMode])

  if (error) {
     // ... (Error handling UI kept same) ...
     return (
      <div style={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        height: '100vh',
        backgroundColor: '#050505',
        color: 'var(--danger)',
        padding: '24px',
        textAlign: 'center',
      }}>
        <div style={{ fontSize: '1.5rem', fontWeight: 'bold', marginBottom: '16px' }}>Hiba történt a betöltés során</div>
        <div style={{ fontSize: '1rem', opacity: 0.8, marginBottom: '32px' }}>{error}</div>
        <button 
          onClick={onClose} 
          style={{
            padding: '12px 32px',
            background: 'var(--bg-panel)',
            color: 'white',
            borderRadius: '12px',
            border: 'var(--glass-border)',
            cursor: 'pointer',
          }}
        >
          Vissza
        </button>
      </div>
    )
  }

  // Determine active image source (Preview or Original)
  const displayUrl = previewUrl 
      ? (previewUrl.startsWith('http') ? previewUrl : (previewUrl.startsWith('/') ? previewUrl : `/${previewUrl}`))
      : (imageUrl ? (imageUrl.startsWith('http') ? imageUrl : (imageUrl.startsWith('/') ? imageUrl : `/${imageUrl}`)) : null)

  const isPreviewLoading = loadingAction === 'preview_preprocessing'

  return (
    <div style={{
      position: 'fixed',
      inset: 0,
      backgroundColor: 'black',
      display: 'flex',
      flexDirection: 'column',
      zIndex: 50,
    }}>
      {loading && <LoaderOverlay />}
      
      {/* Header */}
      <header style={{
        height: '64px',
        borderBottom: '1px solid rgba(255,255,255,0.1)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        padding: '0 24px',
        backgroundColor: 'rgba(15, 15, 15, 0.8)',
        backdropFilter: 'blur(12px)',
      }}>
        {/* ... (Header content kept same) ... */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
          <button 
            onClick={onClose} 
            style={{
              padding: '8px',
              background: 'transparent',
              border: 'none',
              borderRadius: '50%',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              color: 'var(--text-dim)',
              transition: 'all 0.2s',
            }}
            onMouseEnter={(e) => e.currentTarget.style.background = 'rgba(255,255,255,0.1)'}
            onMouseLeave={(e) => e.currentTarget.style.background = 'transparent'}
          >
            <svg style={{ width: '24px', height: '24px' }} fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
          <div style={{ height: '16px', width: '1px', backgroundColor: 'rgba(255,255,255,0.1)' }} />
          <h2 style={{ color: 'white', fontWeight: 500, fontSize: '1rem', margin: 0 }}>
            DINO Felülvizsgálat: <span style={{ color: 'var(--text-dim)', fontFamily: 'monospace', marginLeft: '8px', opacity: 0.6 }}>#{id}</span>
          </h2>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          <button 
            onClick={() => prevId && onPrev && onPrev(prevId)} 
            disabled={!prevId} 
            style={{
              padding: '8px',
              background: 'transparent',
              border: 'none',
              borderRadius: '50%',
              color: 'white',
              cursor: prevId ? 'pointer' : 'not-allowed',
              opacity: prevId ? 1 : 0.3,
              transition: 'all 0.2s',
            }}
          >
            <svg style={{ width: '24px', height: '24px' }} fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
            </svg>
          </button>
          <div style={{ color: 'var(--text-dim)', fontSize: '0.875rem', fontFamily: 'monospace' }}>
            {currentIndex + 1} / {items.length}
          </div>
          <button 
            onClick={() => nextId && onNext && onNext(nextId)} 
            disabled={!nextId} 
            style={{
              padding: '8px',
              background: 'transparent',
              border: 'none',
              borderRadius: '50%',
              color: 'white',
              cursor: nextId ? 'pointer' : 'not-allowed',
              opacity: nextId ? 1 : 0.3,
              transition: 'all 0.2s',
            }}
          >
            <svg style={{ width: '24px', height: '24px' }} fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
            </svg>
          </button>
        </div>
      </header>

      {/* Main Viewport */}
      <main style={{
        flex: 1,
        position: 'relative',
        overflow: 'hidden',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        padding: '32px',
      }}>
        {isPreviewLoading && (
            <div style={{ 
                position: 'absolute', 
                inset: 0, 
                display: 'flex', 
                alignItems: 'center', 
                justifyContent: 'center', 
                background: 'rgba(0,0,0,0.5)', 
                zIndex: 20 
            }}>
                <div className="spinner" style={{ color: 'white' }}>Processing...</div>
            </div>
        )}
        
        {displayUrl && (
          <img
            src={displayUrl}
            alt="Review"
            style={{
              maxWidth: '100%',
              maxHeight: '100%',
              objectFit: 'contain',
              borderRadius: '12px',
              boxShadow: '0 24px 64px rgba(0,0,0,0.5)',
              border: '1px solid rgba(255,255,255,0.05)',
            }}
          />
        )}
        
        {/* Preprocessing Overlay Panel */}
        <div style={{
            position: 'absolute',
            left: '32px',
            top: '32px',
            background: 'rgba(15, 15, 15, 0.8)',
            backdropFilter: 'blur(12px)',
            padding: '16px',
            borderRadius: '12px',
            border: '1px solid rgba(255,255,255,0.1)',
            display: 'flex',
            flexDirection: 'column',
            gap: '12px',
            zIndex: 30
        }}>
            <h4 style={{ margin: 0, fontSize: '0.85rem', color: '#888', textTransform: 'uppercase', letterSpacing: '1px' }}>Preview</h4>
            
            <label style={{ display: 'flex', alignItems: 'center', gap: '8px', cursor: 'pointer', color: '#60a5fa', fontWeight: 500 }}>
                <input type="checkbox" checked={preprocessingOptions.smartRoi} onChange={() => toggleOption('smartRoi')} />
                <span>Smart ROI (FastSAM AI)</span>
            </label>
            
            <div style={{ borderTop: '1px solid rgba(255,255,255,0.1)', marginTop: '8px', paddingTop: '8px' }}>
                <h5 style={{ margin: '0 0 8px 0', fontSize: '0.75rem', color: '#666', textTransform: 'uppercase' }}>Experimental</h5>
                <label style={{ display: 'flex', alignItems: 'center', gap: '8px', cursor: 'pointer', color: '#aaa', marginBottom: '4px' }}>
                    <input type="checkbox" checked={preprocessingOptions.useMask} onChange={() => toggleOption('useMask')} />
                    <span>Mask Objects (YOLO)</span>
                </label>
                <label style={{ display: 'flex', alignItems: 'center', gap: '8px', cursor: 'pointer', color: '#aaa', marginBottom: '4px' }}>
                    <input type="checkbox" checked={preprocessingOptions.useRoi} onChange={() => toggleOption('useRoi')} />
                    <span>Geometric ROI Cut</span>
                </label>
                <label style={{ display: 'flex', alignItems: 'center', gap: '8px', cursor: 'pointer', color: '#aaa', marginBottom: '4px' }}>
                    <input type="checkbox" checked={preprocessingOptions.removeShadows1} onChange={() => toggleOption('removeShadows1')} />
                    <span>Multi-Retinex (MSR)</span>
                </label>
                <label style={{ display: 'flex', alignItems: 'center', gap: '8px', cursor: 'pointer', color: '#aaa' }}>
                    <input type="checkbox" checked={preprocessingOptions.removeShadows2} onChange={() => toggleOption('removeShadows2')} />
                    <span>Local Contrast (CLAHE)</span>
                </label>
            </div>
        </div>
      </main>

      {/* RQI Selector Footer */}
      <footer style={{
        height: '96px',
        borderTop: '1px solid rgba(255,255,255,0.1)',
        backgroundColor: 'rgba(15, 15, 15, 0.8)',
        backdropFilter: 'blur(12px)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        padding: '0 24px',
        gap: '48px',
      }}>
        {/* ... (Footer content kept same) ... */}
         <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          {[1, 2, 3, 4, 5].map((val) => (
            <button
              key={val}
              onClick={() => setRqi(val)}
              style={{
                width: '48px',
                height: '48px',
                borderRadius: '12px',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                fontSize: '1.25rem',
                fontWeight: 'bold',
                transition: 'all 0.2s cubic-bezier(0.175, 0.885, 0.32, 1.275)',
                background: manualRqi === val ? 'var(--primary)' : 'rgba(255,255,255,0.05)',
                color: manualRqi === val ? 'white' : 'var(--text-dim)',
                border: manualRqi === val ? '1px solid rgba(255,255,255,0.2)' : '1px solid transparent',
                transform: manualRqi === val ? 'scale(1.15)' : 'scale(1)',
                boxShadow: manualRqi === val ? '0 8px 20px rgba(59, 130, 246, 0.3)' : 'none',
              }}
            >
              {val}
            </button>
          ))}
        </div>

        <button
          onClick={handleSave}
          disabled={saving || !manualRqi}
          style={{
            minWidth: '200px',
            padding: '12px 32px',
            borderRadius: '12px',
            fontWeight: 'bold',
            fontSize: '1rem',
            transition: 'all 0.2s',
            background: manualRqi ? 'var(--primary)' : 'rgba(255,255,255,0.05)',
            color: manualRqi ? 'white' : 'rgba(255,255,255,0.2)',
            cursor: manualRqi && !saving ? 'pointer' : 'not-allowed',
            border: 'none',
            boxShadow: manualRqi ? '0 8px 24px rgba(59, 130, 246, 0.2)' : 'none',
          }}
          onMouseEnter={(e) => { if (manualRqi && !saving) e.currentTarget.style.transform = 'translateY(-2px)' }}
          onMouseLeave={(e) => { if (manualRqi && !saving) e.currentTarget.style.transform = 'translateY(0)' }}
        >
          {saving ? 'Mentés...' : (fastMode ? 'Automatikus' : 'Mentés (Enter)')}
        </button>

        <button
          onClick={() => predictDinoRqi()}
          disabled={loading}
          style={{
            marginLeft: '12px',
            padding: '12px 24px',
            background: 'var(--bg-glass)',
            border: 'var(--glass-border)',
            borderRadius: '12px',
            color: 'var(--text-primary)',
            cursor: loading ? 'wait' : 'pointer',
            display: 'flex',
            alignItems: 'center',
            gap: '8px',
          }}
        >
          {loading ? 'Elemzés...' : '🤖 DINO AI'}
        </button>
        
        <div style={{ marginLeft: '24px', display: 'flex', alignItems: 'center', gap: '8px' }}>
          <input 
            type="checkbox" 
            id="fastMode" 
            checked={fastMode} 
            onChange={(e) => setFastMode(e.target.checked)}
            style={{ width: '16px', height: '16px', cursor: 'pointer' }}
          />
          <label htmlFor="fastMode" style={{ color: 'var(--text-dim)', fontSize: '0.9rem', cursor: 'pointer', userSelect: 'none' }}>
            Gyors Mód
          </label>
        </div>
      </footer>
    </div>
  )
}
