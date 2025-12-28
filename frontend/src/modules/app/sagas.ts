import { select, take } from 'redux-saga/effects'
import { start } from './slice'

// Reusable Generator for other Sagas
export function* waitForAppStart() {
  // @ts-expect-error selector type issue
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const started = yield select((state: any) => state.app.started)
  if (!started) {
    yield take(start.fulfilled)
  }
}
