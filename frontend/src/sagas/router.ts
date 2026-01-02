import type { SagaIterator } from 'redux-saga'
import { takeLatest, put, call, select } from 'redux-saga/effects'
import { matchPath } from 'react-router-dom'
import { actions as trainingActions } from '../modules/training/slice'
import * as trainingSelectors from '../modules/training/selectors'
import * as routingActions from '../modules/routing/actions'
import { waitForAppStart } from '../modules/app/sagas'
import { ROUTES } from '../routes'
import type { TrainingPoint } from '../modules/training/types'
import type { RootState } from '../store'

// Master Orchestrator for API calls based on Route
function* handleLocationChange(action: { payload: { pathname: string; search: string } }): SagaIterator {
  // Blocking check: Wait for App Start
  yield call(waitForAppStart)

  const { pathname, search } = action.payload
  const searchParams = new URLSearchParams(search)

  const trainingDetailMatch = matchPath(
    { path: ROUTES.TRAINING_DETAIL.path, end: ROUTES.TRAINING_DETAIL.exact },
    pathname,
  ) || matchPath(
    { path: ROUTES.TRAINING_REVIEW.path, end: ROUTES.TRAINING_REVIEW.exact },
    pathname,
  )

  const trainingListMatch = matchPath(
    { path: ROUTES.TRAINING_LIST.path, end: ROUTES.TRAINING_LIST.exact },
    pathname,
  )

  if (trainingDetailMatch) {
    const pointId = trainingDetailMatch.params.id ? parseInt(trainingDetailMatch.params.id, 10) : 0
    if (pointId) {
      yield put(trainingActions.fetchImage(pointId))
    }
  } else if (trainingListMatch) {
    // TRAINING DASHBOARD
    const mode = (searchParams.get('mode') || 'all') as 'pending' | 'reviewed' | 'all'
    
    // Get current filter from state
    const activeMode = yield select(trainingSelectors.selectActiveMode)
    const currentItems: TrainingPoint[] = yield select(trainingSelectors.selectItems)

    // Trigger loads if mode changed OR if we have no items (initial load)
    const isLoading = yield select((state: RootState) => state.training.loading)
    if (!isLoading && (mode !== activeMode || currentItems.length === 0)) {
      yield put(trainingActions.fetchList({ mode: mode.toUpperCase() }))
      yield put(trainingActions.fetchStats({ mode: mode.toUpperCase() }))
    }
  } else if (matchPath({ path: ROUTES.HOME.path, end: ROUTES.HOME.exact }, pathname)) {
    // Entered Map View
    yield put(trainingActions.unmount()) // Ensure training state is cleaned
  }
}

export default [takeLatest(routingActions.locationChange, handleLocationChange)]
