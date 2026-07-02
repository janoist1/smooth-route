import { takeLatestAsync } from 'saga-toolkit'
import { call } from 'redux-saga/effects'
import { actions as appActions } from 'modules/app'

function* handleAppStart() {
  // Real application initialization logic goes here.
  // For now, we simply resolve immediately to signal that the app is ready.
  yield call(console.log, 'App initialized')
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
export default [takeLatestAsync((appActions.start as any).type, handleAppStart)]
