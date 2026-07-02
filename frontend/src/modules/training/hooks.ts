import { useSelector, useDispatch } from 'react-redux'
import { useMemo } from 'react'
import { bindActionCreators } from '@reduxjs/toolkit'
import { actions } from './slice'
import type { TrainingState } from './types'
import * as selectors from './selectors'
import { selectors as settingsSelectors } from '../settings'
import { selectJob } from '../api'
import type { RootState } from '../../store'

export const useTraining = () => {
  const dispatch = useDispatch()
  const state = useSelector(selectors.selectTrainingState)
  const settingsItems = useSelector(settingsSelectors.selectItems) // Get settings for Active Model

  const analysisJobId = state.analysisJobId
  const job = useSelector((root: RootState) => selectJob(root, analysisJobId))

  const boundActions = useMemo(() => bindActionCreators(actions, dispatch), [dispatch])

  // --- Derived State (Calculations) ---
  const activeModel =
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    (settingsItems.find((s: any) => s.key === 'ai_model')?.value as string) || 'YOLOv8 Default'

  // Refactored Job Tracking (Derived from API)
  const rawJobStatus = job ? job.status.toLowerCase() : 'idle'
  
  // Map backend 'pending/queued' to UI 'starting'
  const analysisStatus = (rawJobStatus === 'pending' || rawJobStatus === 'queued') 
    ? 'starting' 
    : rawJobStatus

  const analysisMessage = job ? job.message : ''
  const analysisProgress = job ? job.progress : 0
  const analysisTotal = job ? job.total : 0

  // Training Status derivation:
  // 1. If there's an active job, use its status (normalized).
  // 2. If no job (e.g. request in flight), fallback to local slice state.
  const trainingStatus = (job 
    ? analysisStatus 
    : (state.trainingStatus === 'running' || state.trainingStatus === 'starting') 
      ? state.trainingStatus 
      : 'idle') as TrainingState['trainingStatus']
  
  // Extract exports if job is completed
  let exports = null
  if (job?.result?.exports) {
      // Clone to avoid mutating ReadOnly Redux state
      exports = { ...job.result.exports }
      // Normalize snake_case to camelCase
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      if ((exports as any).notebook_path) exports.notebookPath = (exports as any).notebook_path
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      if ((exports as any).dataset_path) exports.datasetPath = (exports as any).dataset_path
  } else if (state.exports) {
      // Fallback to local state if exists (legacy)
      exports = state.exports
  }

  return {
    ...state,
    ...boundActions,
    // Overrides / Derived
    analysisStatus,
    analysisMessage,
    analysisProgress,
    analysisTotal,
    trainingStatus,
    exports, 
    // Enhanced props
    activeModel,
  }
}
