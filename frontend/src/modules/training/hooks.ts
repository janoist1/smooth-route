import { useSelector, useDispatch } from 'react-redux'
import { useMemo } from 'react'
import { bindActionCreators } from '@reduxjs/toolkit'
import { actions } from './slice'
import * as selectors from './selectors'

export const useTraining = () => {
  const dispatch = useDispatch()
  const state = useSelector(selectors.selectTrainingState)

  const boundActions = useMemo(() => bindActionCreators(actions, dispatch), [dispatch])

  return {
    ...state,
    ...boundActions,
  }
}
