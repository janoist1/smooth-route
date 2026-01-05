import React, { useMemo } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { 
  AnalysisPanel, 
  TrainingList, 
  TrainingStatsView, 
  useTraining 
} from 'modules/training'
import { ROUTES, buildPath } from '../../routes'
import { usePagination, SegmentedControl } from 'modules/ui'
import { PAGE_SIZE } from '../../constants'
import MainLayout from '../../components/MainLayout'
import { Check, Clock, Layers } from 'lucide-react'

const TrainingDashboardPage: React.FC = () => {
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const currentMode = searchParams.get('mode') || 'all'

  // --- Data & Logic (from Training Module) ---
  const {
    // List Data
    items,
    loading,
    error,
    totalCount,
    // Stats & Analysis
    globalStats,
    runAnalysis,
    resetAnalysisJob,
    analysisStatus,
    analysisMessage,
    analysisProgress,
    analysisTotal,
    startTraining,
    stopJob,
    trainingStatus,
    analysisJobId,
    exports,
    activeModel
  } = useTraining()

  // --- Pagination Logic (from UI Module) ---
  const { currentPage, totalPages, goToPage } = usePagination({
    totalCount: totalCount || 0,
    pageSize: PAGE_SIZE
  })

  // --- Event Handlers ---
  const handleFilterChange = (mode: string) => {
    navigate(`${ROUTES.TRAINING_LIST.path}?mode=${mode}&page=1`)
  }

  const handleItemClick = (id: string | number) => {
    navigate(buildPath(ROUTES.TRAINING_REVIEW, { id }))
  }
  
  const handlePageChange = (page: number) => {
      goToPage(page)
      window.scrollTo({ top: 0, behavior: 'smooth' })
  }

  // --- Derived View Data ---
  const stats = useMemo(() => {
    if (!globalStats) return null
    return {
      total: globalStats.total,
      reviewNeeded: globalStats.pending,
      annotated: globalStats.annotated,
      avgRqi: globalStats.avgRqi.toFixed(1),
      good: globalStats.goodCount,
      fair: globalStats.fairCount,
      poor: globalStats.poorCount,
    }
  }, [globalStats])

  return (
    <MainLayout>
      <div style={{ padding: '24px', maxWidth: '1400px', margin: '0 auto', paddingBottom: '100px' }}>
        {/* 1. Header */}
        <div style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'flex-start',
          marginBottom: '32px',
        }}>
          <div>
            <h1 style={{ fontSize: '2rem', fontWeight: 'bold', color: 'white', marginBottom: '8px' }}>
              Training Dashboard
            </h1>
            <p style={{ color: '#9ca3af' }}>Manage and annotate analysis results</p>
          </div>
        </div>

        {/* 2. Analysis Control Panel */}
        <div style={{ marginTop: '8px', marginBottom: '32px' }}>
          <AnalysisPanel
            analysisStatus={analysisStatus}
            analysisMessage={analysisMessage}
            analysisProgress={analysisProgress}
            analysisTotal={analysisTotal}
            onRunAnalysis={(params) => runAnalysis(params)}
            onStartTraining={() => startTraining()}
            onStopJob={() => {
              if (analysisJobId) stopJob(analysisJobId)
            }}
            onResetJob={() => resetAnalysisJob()}
            trainingStatus={trainingStatus}
            pendingAnalysisCount={globalStats?.pendingAnalysis || 0}
            modelName={activeModel}
            exports={exports}
          />
        </div>

        {/* 3. Statistics */}
        {stats && <TrainingStatsView stats={stats} />}

        {/* 4. Filter Controls (Widget) */}
        <div style={{
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

        {/* 5. Main List & Pagination */}
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

export default TrainingDashboardPage
