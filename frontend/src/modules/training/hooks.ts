import { useSelector, useDispatch } from 'react-redux'
import { bindActionCreators } from '@reduxjs/toolkit'
import { actions } from './slice'
import * as selectors from './selectors'

export const useTraining = () => {
  const dispatch = useDispatch()
  const state = useSelector(selectors.selectTrainingState)

  return {
    ...state,
    ...bindActionCreators(actions, dispatch),
  }
}
