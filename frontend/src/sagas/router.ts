import type { SagaIterator } from 'redux-saga'
import { takeLatest, put, call, select } from 'redux-saga/effects'
import { matchPath } from 'react-router-dom'
import { actions as trainingActions, selectors as trainingSelectors } from 'modules/training'
import { actions as mapActions } from 'modules/map'
import { actions as settingsActions } from 'modules/settings'
import { actions as routingActions } from 'modules/routing'
import { waitForAppStart } from 'modules/app'
import { PAGE_SIZE } from '../constants'
import { ROUTES } from '../routes'
import type { TrainingPoint } from 'modules/training/types'
import type { RootState } from '../store'

// Master Orchestrator for API calls based on Route
function* handleLocationChange(action: {
  payload: { pathname: string; search: string }
}): SagaIterator {
  // Blocking check: Wait for App Start
  yield call(waitForAppStart)

  const { pathname, search } = action.payload
  const searchParams = new URLSearchParams(search)

  const trainingDetailMatch =
    matchPath({ path: ROUTES.TRAINING_DETAIL.path, end: ROUTES.TRAINING_DETAIL.exact }, pathname) ||
    matchPath({ path: ROUTES.TRAINING_REVIEW.path, end: ROUTES.TRAINING_REVIEW.exact }, pathname)

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
    const page = parseInt(searchParams.get('page') || '1', 10)
    const offset = (page - 1) * PAGE_SIZE

    // Get current filter from state
    const activeMode = yield select(trainingSelectors.selectActiveMode)
    const currentItems: TrainingPoint[] = yield select(trainingSelectors.selectItems)
    const currentOffset: number = yield select(trainingSelectors.selectOffset)

    // Trigger loads if mode changed OR if we have no items (initial load) OR if offset mismatch
    const isLoading = yield select((state: RootState) => state.training.loading)

    // We fetch if:
    // 1. Not loading
    // 2. AND (Mode changed OR Items empty OR Offset changed)
    // Note: We might want strictly checking if the *current* data matches the URL requirements.
    if (
      !isLoading &&
      (mode !== activeMode || currentItems.length === 0 || currentOffset !== offset)
    ) {
      yield put(trainingActions.fetchList({ mode: mode.toUpperCase(), offset }))
      yield put(trainingActions.fetchStats({ mode: mode.toUpperCase() }))
    }

    // Always check for active jobs and ensuring settings when visiting dashboard
    yield put(trainingActions.reconnectJob())
    yield put(settingsActions.fetchSettings())
  } else if (matchPath({ path: ROUTES.HOME.path, end: ROUTES.HOME.exact }, pathname)) {
    // Entered Map View
    yield put(trainingActions.unmount()) // Ensure training state is cleaned

    // SYNC MAP URL -> REDUX
    const lat = searchParams.get('lat')
    const lng = searchParams.get('lng')
    const z = searchParams.get('z')

    if (lat && lng && z) {
      yield put(
        mapActions.setViewport({
          center: [parseFloat(lat), parseFloat(lng)],
          zoom: parseInt(z, 10),
        }),
      )
    }
  } else if (matchPath({ path: ROUTES.SETTINGS.path, end: ROUTES.SETTINGS.exact }, pathname)) {
    // ENTERED SETTINGS
    yield put(settingsActions.fetchSettings())
  }
}

export default [takeLatest(routingActions.locationChange, handleLocationChange)]
