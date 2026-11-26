import { describe, expect, it, vi } from 'vitest'
import { runSaga, stdChannel } from 'redux-saga'
import { all } from 'redux-saga/effects'

vi.mock('modules/app', () => ({ waitForAppStart: vi.fn() }))
import sagas from './router'

describe('quick-label routing', () => {
  it('does not dispatch admin label loading from an anonymous deep link', async () => {
    const channel = stdChannel()
    const dispatch = vi.fn()
    const task = runSaga({ channel, dispatch }, function* () { yield all(sagas) })
    try {
      channel.put({ type: 'ROUTER/LOCATION_CHANGE', payload: { pathname: '/training/quick', search: '' } })
      await Promise.resolve()
      expect(dispatch).not.toHaveBeenCalled()
    } finally { task.cancel() }
  })
})
