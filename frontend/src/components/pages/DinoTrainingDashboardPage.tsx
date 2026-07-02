import React from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { TrainingList, DinoTrainingStats, DinoTrainingPanel, useTraining } from 'modules/training'
import { ROUTES, buildPath } from '../../routes'
import { usePagination, SegmentedControl } from 'modules/ui'
import { PAGE_SIZE } from '../../constants'
import MainLayout from '../../components/MainLayout'
import { Layers, Clock, Check } from 'lucide-react'

const DinoTrainingDashboardPage: React.FC = () => {
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const currentMode = searchParams.get('mode') || 'all'

  const {
    items,
    loading,
    error,
    globalStats,
    totalCount,
    fetchList,
    // Job Control
    startTraining,
    stopJob,
    trainingStatus,
    analysisStatus,
    analysisMessage,
    analysisProgress,
    analysisTotal,
    analysisJobId,
    resetAnalysisJob,
    reconnectJob,
    exports, 
    runAnalysis,
  } = useTraining()

  // --- Pagination Logic (from UI Module) ---
  const { currentPage, totalPages, goToPage } = usePagination({
    totalCount: totalCount || 0,
    pageSize: PAGE_SIZE,
  })

  // --- Event Handlers ---
  const handleItemClick = (id: string | number) => {
    navigate(buildPath(ROUTES.TRAINING_DINO_REVIEW, { id }))
  }

  const handlePageChange = (page: number) => {
    goToPage(page)
    window.scrollTo({ top: 0, behavior: 'smooth' })
  }

  const handleFilterChange = (mode: string) => {
    navigate(`${ROUTES.TRAINING_DINO_LIST.path}?mode=${mode}`)
  }

  const handleRefresh = () => {
    fetchList({ offset: (currentPage - 1) * PAGE_SIZE, mode: currentMode, model: 'dino' })
  }

  // Poll for active job on mount (in case of refresh)
  React.useEffect(() => {
    reconnectJob()
  }, [reconnectJob])

  return (
    <MainLayout>
      <div
        style={{ padding: '24px', maxWidth: '1400px', margin: '0 auto', paddingBottom: '100px' }}>
        {/* 1. Header */}
        <div
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'flex-start',
            marginBottom: '32px',
          }}>
          <div>
            <h1
              style={{ fontSize: '2rem', fontWeight: 'bold', color: 'white', marginBottom: '8px' }}>
              DINO Classification Training
            </h1>
            <p style={{ color: '#9ca3af' }}>Manual RQI (1-5) labeling for base model training.</p>
          </div>
          <button
            onClick={handleRefresh}
            style={{
              padding: '8px 16px',
              background: 'rgba(255,255,255,0.05)',
              color: 'var(--primary)',
              borderRadius: '8px',
              border: '1px solid rgba(255,255,255,0.1)',
              cursor: 'pointer',
              fontSize: '0.875rem'
            }}
            onMouseEnter={(e) => e.currentTarget.style.background = 'rgba(255,255,255,0.1)'}
            onMouseLeave={(e) => e.currentTarget.style.background = 'rgba(255,255,255,0.05)'}
          >
            Refresh
          </button>
        </div>

        {/* 2. Training Controls Panel */}
        <div style={{ marginBottom: '32px' }}>
          <DinoTrainingPanel 
            trainingStatus={trainingStatus}
            analysisStatus={analysisStatus}
            analysisMessage={analysisMessage}
            analysisProgress={analysisProgress}
            analysisTotal={analysisTotal}
            analysisJobId={analysisJobId}
            exports={exports}
            onStartTraining={() => startTraining({ modelType: 'DINO' })}
            onRunAnalysis={(reanalyze) => runAnalysis({ strategy: 'CLASSIFICATION', limit: 0, reanalyze })}
            onStopJob={(id) => stopJob(id)}
            onResetJob={() => resetAnalysisJob()}
          />
        </div>
          
        {/* 3. Stats */}
        <div style={{ marginBottom: '32px' }}>
          <DinoTrainingStats stats={globalStats} />
        </div>

        {/* 4. Filter Controls */}
        <div
          style={{
            marginBottom: '24px',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
          }}>
          <SegmentedControl
            options={[
              { value: 'all', label: 'All Items', icon: <Layers size={14} /> },
              { value: 'pending', label: 'Review Needed', icon: <Clock size={14} /> },
              { value: 'reviewed', label: 'Reviewed', icon: <Check size={14} /> },
            ]}
            value={currentMode}
            onChange={handleFilterChange}
          />
        </div>

        {/* 4. Main List & Pagination */}
        <TrainingList
            items={items}
            loading={loading}
            error={error}
            onItemClick={handleItemClick}
            currentPage={currentPage}
            totalPages={totalPages}
            onPageChange={handlePageChange}
            onRetry={() => handlePageChange(1)}
        />
      </div>
    </MainLayout>
  )
}

export default DinoTrainingDashboardPage
