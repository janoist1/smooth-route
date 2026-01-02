import React, { useEffect } from 'react'
import { useDispatch, useSelector } from 'react-redux'
import { bindActionCreators } from 'redux'
import { actions } from './slice'
import * as selectors from './selectors'

export { useDispatch, useSelector }

type DynamicState = {
  loading: boolean
}

// eslint-disable-next-line @typescript-eslint/no-unused-vars
export const useAppStart = (_params = { public: false }) => {
  const { start } = useApp()
  const started = useSelector(selectors.selectAppStarted)

  useEffect(() => {
    if (!started) {
      start()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])
}

export const useApp = (): DynamicState &
  ReturnType<typeof selectors.selectRoot> &
  typeof actions => {
  const root = useSelector(selectors.selectRoot)

  const dispatch = useDispatch()

  const boundActions = React.useMemo(() => bindActionCreators(actions, dispatch), [dispatch])

  return {
    ...boundActions,
    ...root,
    loading: false, // implementation needed if we want to track global loading
  }
}
