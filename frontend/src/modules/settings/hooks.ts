import { useDispatch, useSelector } from 'react-redux'
import { bindActionCreators } from '@reduxjs/toolkit'
import * as actions from './slice'
import * as selectors from './selectors'

export const useSettings = () => {
  const dispatch = useDispatch()

  const state = useSelector(selectors.selectRoot)
  const categories = useSelector(selectors.selectCategories)

  const boundActions = bindActionCreators(
    {
      fetchSettings: actions.fetchSettings,
      updateSetting: actions.updateSetting,
      applyPreset: actions.applyPreset,
    },
    dispatch,
  )

  return {
    ...state,
    categories,
    ...boundActions,
  }
}

/** Read-only access to the configured RQI display source ('yolo' | 'dino' | 'both'). */
export const useRqiDisplaySource = () => useSelector(selectors.selectRqiDisplaySource)
