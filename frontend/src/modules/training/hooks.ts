import { useSelector, useDispatch } from 'react-redux'
import { useMemo } from 'react'
import { bindActionCreators } from '@reduxjs/toolkit'
import { actions } from './slice'
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
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const analysisStatus = job ? (job.status.toLowerCase() as any) : 'idle'
  const analysisMessage = job ? job.message : ''
  const analysisProgress = job ? job.progress : 0
  const analysisTotal = job ? job.total : 0
  const trainingStatus = analysisStatus // Alias for compatibility
  
  // Extract exports if job is completed
  let exports = null
  if (job?.result?.exports) {
      // Clone to avoid mutating ReadOnly Redux state
      exports = { ...job.result.exports }
      // Normalize snake_case to camelCase if needed, but keeping it simple for now
      // The UI expects { notebookPath, datasetPath, instructions }
      // The API result might have notebook_path.
      // Let's normalize safely
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
