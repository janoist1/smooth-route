import React, { useMemo, useEffect } from 'react'
import { useDispatch } from 'react-redux'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { 
  Check, 
  Clock, 
  Layers
} from 'lucide-react'
import { useTraining } from '../hooks'
import { ROUTES, buildPath } from '../../../routes'
import TrainingStats from './TrainingStats'
import AnalysisPanel from './AnalysisPanel'
import { 
  SegmentedControl, 
  DataGrid, 
  type ColumnDef
} from '../../ui'
import type { TrainingPoint } from '../types'

const TrainingDashboard: React.FC = () => {
  const navigate = useNavigate()
  
  // --- State & Actions ---
  const { 
    items, 
    loading, 
    error, 
    fetchList, 
    globalStats,
    hasMore,
    offset,
    activeMode,
    runAnalysis,
    resetAnalysisJob,
    analysisStatus,
    analysisMessage,
    analysisProgress,
    analysisTotal,
    startTraining,
    stopJob,
    trainingStatus
  } = useTraining()
  
  const dispatch = useDispatch()

  const [searchParams] = useSearchParams()
  const currentMode = searchParams.get('mode') || 'all' // This currentMode is from the URL

  const handleLoadMore = () => {
    if (!loading && hasMore) {
      // Use the activeMode from the hook, which reflects the mode for the current list
      fetchList({ mode: activeMode.toUpperCase(), offset })
    }
  }

  const handleFilterChange = (newMode: string) => {
    // Just navigate, the router saga will handle the rest (clearing list only if mode changed)
    navigate(`${ROUTES.TRAINING_LIST.path}?mode=${newMode}`)
  }
  
  // Reconnect to active job on mount
  useEffect(() => {
    dispatch({ type: 'training/reconnectJob' })
  }, [dispatch])

  // --- Stats Calculation ---
  const stats = useMemo(() => {
    if (!globalStats) return null
    return { 
      total: globalStats.total, 
      reviewNeeded: globalStats.pending, 
      annotated: globalStats.annotated, 
      avgRqi: globalStats.avgRqi.toFixed(1), 
      good: globalStats.goodCount, 
      fair: globalStats.fairCount, 
      poor: globalStats.poorCount 
    }
  }, [globalStats])

  // --- Table Configuration ---
  const columns: ColumnDef<TrainingPoint>[] = [
    {
      key: 'image',
      header: 'Image',
      width: '100px',
      render: (item: TrainingPoint) => (
        <div style={{ width: '80px', height: '60px', borderRadius: '4px', overflow: 'hidden', background: '#374151' }}>
          {item.imageUrl && (
            <img 
              src={item.imageUrl.startsWith('/') ? item.imageUrl : `/${item.imageUrl}`} 
              alt="" 
              style={{ width: '100%', height: '100%', objectFit: 'cover' }} 
            />
          )}
        </div>
      )
    },
    {
      key: 'id',
      header: 'ID',
      width: '80px',
      render: (item: TrainingPoint) => <code style={{ color: '#9ca3af' }}>#{item.id}</code>
    },
    {
      key: 'rqi',
      header: 'AI RQI (1=Best)',
      render: (item: TrainingPoint) => {
        const val = item.rqiScore
        if (val === undefined || val === null) return <span style={{color: '#6b7280'}}>-</span>
        let color = '#ef4444' // Poor (> 3.5)
        if (val <= 2.0) color = '#4ade80' // Good
        else if (val <= 3.5) color = '#facc15' // Fair
        return <span style={{ fontWeight: 'bold', color }}>{val.toFixed(1)}</span>
      }
    },
    {
      key: 'manual',
      header: 'Ground Truth (1=Best)',
      render: (item: TrainingPoint) => {
        if (item.manualRqi || item.manualRqi === 0) {
          return (
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <Check size={14} style={{ color: '#4ade80' }} />
              <span style={{ color: '#e5e7eb', fontWeight: 500 }}>{item.manualRqi.toFixed(1)}</span>
            </div>
          )
        }
        return <span style={{ color: '#6b7280', fontStyle: 'italic' }}>Pending</span>
      }
    },
    {
      key: 'tags',
      header: 'Tags',
      render: (item: TrainingPoint) => (
        <div style={{ display: 'flex', gap: '4px', flexWrap: 'wrap' }}>
          {item.manualTags?.map((tag: string) => (
            <span key={tag} style={{ 
              padding: '2px 8px', borderRadius: '12px', background: 'rgba(59, 130, 246, 0.1)', 
              color: '#60a5fa', fontSize: '11px', border: '1px solid rgba(59, 130, 246, 0.2)'
            }}>
              {tag}
            </span>
          ))}
          {!item.manualTags?.length && <span style={{ color: '#4b5563' }}>-</span>}
        </div>
      )
    }
  ]

  // --- Render ---
  return (
    <div style={{ padding: '24px', maxWidth: '1400px', margin: '0 auto', paddingBottom: '100px' }}>
      {/* Header Section */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '32px' }}>
        <div>
          <h1 style={{ fontSize: '2rem', fontWeight: 'bold', color: 'white', marginBottom: '8px' }}>Training Dashboard</h1>
          <p style={{ color: '#9ca3af' }}>Manage and annotate analysis results</p>
        </div>
      </div>

      <div style={{ marginTop: '8px', marginBottom: '32px' }}>
        <AnalysisPanel 
          analysisStatus={analysisStatus}
          analysisMessage={analysisMessage}
          analysisProgress={analysisProgress}
          analysisTotal={analysisTotal}
          onRunAnalysis={(params: { strategy: string; limit: number; reanalyze: boolean }) => runAnalysis(params)}
          onStartTraining={() => startTraining()}
          onStopJob={() => stopJob()}
          onResetJob={() => resetAnalysisJob()}
          trainingStatus={trainingStatus}
          pendingAnalysisCount={globalStats?.pendingAnalysis || 0}
        />
      </div>

      {stats && <TrainingStats stats={stats} />}

      {/* List Section */}
      <div style={{ marginBottom: '24px', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <SegmentedControl 
          options={[
            { value: 'pending', label: 'Review Needed', icon: <Clock size={14} /> },
            { value: 'reviewed', label: 'Reviewed', icon: <Check size={14} /> },
            { value: 'all', label: 'All Items', icon: <Layers size={14} /> }
          ]}
          value={currentMode}
          onChange={handleFilterChange}
        />
      </div>

      {error ? (
        <div style={{ padding: '40px', textAlign: 'center', background: 'rgba(239, 68, 68, 0.05)', borderRadius: '16px', border: '1px solid rgba(239, 68, 68, 0.2)' }}>
          <p style={{ color: '#f87171', marginBottom: '16px' }}>{error}</p>
          <button 
            onClick={() => fetchList({ mode: currentMode.toUpperCase(), offset: 0 })}
            style={{ padding: '8px 20px', borderRadius: '8px', background: '#ef4444', color: 'white', border: 'none', cursor: 'pointer' }}
          >
            Try Again
          </button>
        </div>
      ) : (
        <>
          <DataGrid 
            columns={columns} 
            data={items} 
            loading={loading && items.length === 0}
            onRowClick={(item: TrainingPoint) => navigate(buildPath(ROUTES.TRAINING_DETAIL, { id: item.id }))}
            emptyMessage="No training data found"
          />

          {hasMore && (
            <div style={{ display: 'flex', justifyContent: 'center', marginTop: '20px' }}>
              <button
                onClick={handleLoadMore}
                disabled={loading}
                style={{
                  background: 'rgba(255, 255, 255, 0.05)',
                  border: '1px solid rgba(255, 255, 255, 0.1)',
                  padding: '10px 24px',
                  borderRadius: '8px',
                  color: 'white',
                  cursor: loading ? 'not-allowed' : 'pointer',
                  fontSize: '14px',
                  fontWeight: 500,
                  transition: 'all 0.2s'
                }}
              >
                {loading ? 'Loading...' : 'Load More'}
              </button>
            </div>
          )}
        </>
      )}
    </div>
  )
}

export default TrainingDashboard
