import { useSelector, useDispatch } from 'react-redux'
import { useMemo } from 'react'
import { bindActionCreators } from '@reduxjs/toolkit'
import { actions } from './slice'
import * as selectors from './selectors'
import { selectors as settingsSelectors } from '../settings'

export const useTraining = () => {
  const dispatch = useDispatch()
  const state = useSelector(selectors.selectTrainingState)
  const settingsItems = useSelector(settingsSelectors.selectItems) // Get settings for Active Model

  const boundActions = useMemo(() => bindActionCreators(actions, dispatch), [dispatch])

  // --- Derived State (Calculations) ---
  const activeModel = (settingsItems.find(s => s.key === 'ai_model')?.value as string) || 'YOLOv8 Default'

  return {
    ...state,
    ...boundActions,
    // Enhanced props
    activeModel,
  }
}
