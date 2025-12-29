import { takeLatest, put, call } from 'redux-saga/effects'
import { matchPath } from 'react-router-dom'
import { actions as trainingActions } from '../modules/training'
import { actions as routingActions } from '../modules/routing'
import { waitForAppStart } from '../modules/app'
import { ROUTES } from '../routes'

// Master Orchestrator for API calls based on Route
// eslint-disable-next-line @typescript-eslint/no-explicit-any
function* handleLocationChange(action: any) {
  // Blocking check: Wait for App Start
  yield call(waitForAppStart)
  console.log('Orchestrator: App Started, proceeding.')

  const { pathname } = action.payload
  console.log('Orchestrator: Route Changed to', pathname)

  const trainingMatch = matchPath(
    { path: ROUTES.TRAINING.path, end: ROUTES.TRAINING.exact },
    pathname,
  )

  if (trainingMatch) {
    // Entered Training View
    // trainingMatch.params.id will be string.
    const pointId = trainingMatch.params.id ? parseInt(trainingMatch.params.id, 10) : 0
    if (pointId) {
      yield put(trainingActions.fetchImage(pointId))
    }
  } else if (matchPath({ path: ROUTES.HOME.path, end: ROUTES.HOME.exact }, pathname)) {
    // Entered Map View
    yield put(trainingActions.unmount()) // Ensure training state is cleaned
  }
}

export default [takeLatest(routingActions.LOCATION_CHANGE, handleLocationChange)]
