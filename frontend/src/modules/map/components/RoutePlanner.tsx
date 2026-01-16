import { useState } from 'react'
import { Navigation, Play, MapPin, X } from 'lucide-react'
import { useMap } from '../hooks'

const RoutePlanner = () => {
  const [isOpen, setIsOpen] = useState(true)
  
  const { 
    isPlanningRoute, 
    isAnalyzingRoute, 
    routeAnalysisJobId, 
    error, 
    routePoints,
    origin, 
    destination, 
    pickingLocationFor,
    job,
    
    // Actions
    clearRoute,
    cancelPickingLocation,
    planRoute,
    analyzeRoute,
    setRouteForm,
    startPickingLocation,
  } = useMap()
  
  // Parse job status for UI (safely handle null job)
  const { progress: jobProgress, status: jobStatus, message: jobMessage } = job || { progress: 0, status: null, message: null }
  
  const handleClose = () => {
    setIsOpen(false)
    clearRoute()
    cancelPickingLocation()
  }

  const handlePlan = () => {
    if (!origin || !destination) return
    planRoute({ origin, destination })
  }
  
  const handleAnalyze = () => {
    if (!origin || !destination) return
    analyzeRoute({ origin, destination })
  }

  const handleInputChange = (field: 'origin' | 'destination', value: string) => {
      setRouteForm({ field, value })
  }

  const handlePickLocation = (field: 'origin' | 'destination') => {
      if (pickingLocationFor === field) {
          cancelPickingLocation()
      } else {
          startPickingLocation(field)
      }
  }
  
  // Highlight style for active picking button
  const getPickBtnStyle = (field: 'origin' | 'destination') => ({
        background: pickingLocationFor === field ? '#3b82f6' : '#27272a',
        border: pickingLocationFor === field ? '1px solid #60a5fa' : '1px solid #3f3f46',
        borderRadius: '6px',
        width: '36px',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        cursor: 'pointer',
        color: '#e5e7eb',
        transition: 'all 0.2s ease'
  })

  if (!isOpen) {
    return (
      <button 
        onClick={() => setIsOpen(true)}
        style={{
            position: 'absolute',
            top: '20px',
            left: '60px', // Moved right to avoid potential overlap with leaflet controls
            zIndex: 1000,
            background: 'var(--bg-panel, #222)',
            border: 'var(--glass-border, 1px solid #444)',
            color: '#60a5fa', // blue-400
            width: '48px',
            height: '48px',
            borderRadius: '50%',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            boxShadow: '0 4px 6px rgba(0,0,0,0.3)',
            cursor: 'pointer'
        }}
        title="Útvonaltervezés és Elemzés"
      >
        <Navigation size={24} />
      </button>
    )
  }

  return (
    <div style={{
        position: 'absolute',
        top: '20px',
        left: '60px',
        zIndex: 1000,
        width: '320px',
        backgroundColor: 'var(--bg-panel, rgba(24, 24, 27, 0.95))',
        backdropFilter: 'blur(12px)',
        border: 'var(--glass-border, 1px solid rgba(255,255,255,0.1))',
        borderRadius: '12px',
        boxShadow: '0 10px 15px -3px rgba(0, 0, 0, 0.5)',
        padding: '16px',
        color: 'var(--text-main, #fff)',
        display: 'flex',
        flexDirection: 'column',
        gap: '16px'
    }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderBottom: '1px solid rgba(255,255,255,0.1)', paddingBottom: '8px' }}>
        <h3 style={{ margin: 0, fontSize: '1.1rem', display: 'flex', alignItems: 'center', gap: '8px' }}>
            <Navigation size={20} color="#3b82f6" />
            Útvonaltervező
        </h3>
        <button onClick={handleClose} style={{ background: 'transparent', border: 'none', color: '#9ca3af', cursor: 'pointer', padding: '4px' }}>
            <X size={20} />
        </button>
      </div>
      
      {/* Inputs */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
        <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
            <label style={{ fontSize: '0.75rem', textTransform: 'uppercase', fontWeight: 700, letterSpacing: '0.05em', color: '#9ca3af' }}>Start (Cím vagy Koord.)</label>
            <div style={{ display: 'flex', gap: '8px' }}>
                <input 
                    value={origin}
                    onChange={(e) => handleInputChange('origin', e.target.value)}
                    placeholder="pl. Budapest, Hősök tere"
                    style={{
                        background: '#09090b',
                        border: '1px solid #3f3f46',
                        borderRadius: '6px',
                        padding: '8px 12px',
                        color: 'white',
                        fontSize: '0.875rem',
                        outline: 'none',
                        flex: 1
                    }}
                    disabled={isPlanningRoute}
                />
                <button 
                    onClick={() => handlePickLocation('origin')}
                    title={pickingLocationFor === 'origin' ? 'Kijelölés folyamatban...' : 'Kijelölés a térképen'}
                    style={getPickBtnStyle('origin')}
                >
                    <MapPin size={16} color={pickingLocationFor === 'origin' ? "#fff" : "#e5e7eb"} />
                </button>
            </div>
        </div>
        
        <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
            <label style={{ fontSize: '0.75rem', textTransform: 'uppercase', fontWeight: 700, letterSpacing: '0.05em', color: '#9ca3af' }}>Cél (Cím vagy Koord.)</label>
            <div style={{ display: 'flex', gap: '8px' }}>
                <input 
                    value={destination}
                    onChange={(e) => handleInputChange('destination', e.target.value)}
                    placeholder="pl. Szeged, Dóm tér"
                    style={{
                        background: '#09090b',
                        border: '1px solid #3f3f46',
                        borderRadius: '6px',
                        padding: '8px 12px',
                        color: 'white',
                        fontSize: '0.875rem',
                        outline: 'none',
                        flex: 1
                    }}
                />
                <button 
                    onClick={() => handlePickLocation('destination')}
                    title={pickingLocationFor === 'destination' ? 'Kijelölés folyamatban...' : 'Kijelölés a térképen'}
                    style={getPickBtnStyle('destination')}
                >
                    <MapPin size={16} color={pickingLocationFor === 'destination' ? "#fff" : "#e5e7eb"} />
                </button>
            </div>
        </div>
      </div>
      
      {/* Actions */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
        <button 
            onClick={handlePlan}
            disabled={!origin || !destination || isPlanningRoute}
            style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                gap: '8px',
                background: isPlanningRoute ? '#2563eb' : '#3b82f6', // blue-600 : blue-500
                color: 'white',
                padding: '10px',
                borderRadius: '6px',
                border: 'none',
                fontWeight: 500,
                cursor: (!origin || !destination || isPlanningRoute) ? 'not-allowed' : 'pointer',
                opacity: (!origin || !destination || isPlanningRoute) ? 0.7 : 1,
                transition: 'background 0.2s'
            }}
        >
            {isPlanningRoute ? (
                <>Tervezés...</>
            ) : (
                <><MapPin size={16} /> Útvonal Mutatása</>
            )}
        </button>
        
        {routePoints && (
             <button 
                onClick={handleAnalyze}
                disabled={isAnalyzingRoute}
                style={{
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    gap: '8px',
                    background: isAnalyzingRoute ? '#059669' : '#10b981', // emerald-600 : emerald-500
                    color: 'white',
                    padding: '10px',
                    borderRadius: '6px',
                    border: 'none',
                    fontWeight: 500,
                    cursor: isAnalyzingRoute ? 'not-allowed' : 'pointer',
                    opacity: isAnalyzingRoute ? 0.7 : 1,
                    marginTop: '8px',
                    borderTop: '1px solid rgba(255,255,255,0.1)',
                    paddingTop: '16px'
                }}
            >
                {isAnalyzingRoute ? (
                    <>Elemzés folyamatban...</>
                ) : (
                    <><Play size={16} /> Elemzés Indítása</>
                )}
            </button>
        )}
      </div>

      {routeAnalysisJobId && (
          <div style={{
              background: 'rgba(6, 78, 59, 0.3)', // emerald-900/30
              border: '1px solid rgba(6, 95, 70, 0.5)', // emerald-800
              padding: '12px',
              borderRadius: '6px',
              fontSize: '0.875rem',
              color: '#d1fae5' // emerald-100
          }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '4px' }}>
                  <p style={{ margin: 0, fontWeight: 500 }}>{jobStatus === 'completed' ? 'Kész!' : 'Folyamatban...'}</p>
                  <p style={{ margin: 0, fontWeight: 700 }}>{jobProgress}%</p>
              </div>
              
              <div style={{ width: '100%', height: '6px', background: 'rgba(0,0,0,0.3)', borderRadius: '3px', marginBottom: '8px', overflow: 'hidden' }}>
                  <div style={{ 
                      width: `${jobProgress}%`, 
                      height: '100%', 
                      background: '#34d399', // emerald-400
                      transition: 'width 0.3s ease'
                  }} />
              </div>

              <p style={{ margin: 0, fontSize: '0.8rem', opacity: 0.9 }}>{jobMessage || 'Várakozás...'}</p>
              <p style={{ margin: '4px 0 0 0', fontSize: '0.7rem', opacity: 0.5, fontFamily: 'monospace' }}>ID: {routeAnalysisJobId}</p>
          </div>
      )}
      
      {error && <div style={{ color: '#f87171', fontSize: '0.875rem', marginTop: '8px' }}>{error}</div>}
      
      <div style={{ fontSize: '0.75rem', color: '#71717a', fontStyle: 'italic' }}>
        Tipp: Írj be egy címet (pl. Budapest, Astoria) vagy koordinátákat.
      </div>
    </div>
  )
}

export default RoutePlanner
