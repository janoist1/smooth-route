// The page renders one big button per level of the shared RQI scale (name
// first) and a tap stores that level's value.
import { describe, expect, it, vi } from 'vitest'
import { act, fireEvent, render, screen } from '@testing-library/react'
import { Provider } from 'react-redux'
import { combineReducers, configureStore } from '@reduxjs/toolkit'
import createSagaMiddleware from 'redux-saga'
import { all, delay } from 'redux-saga/effects'
import { RQI_LEVELS } from '../../ui'

const saved: unknown[] = []

vi.mock('../../graphql', () => ({
  gql: (source: string) => source,
  *gqlQuery(options: { query: string }) {
    yield delay(1)
    if (options.query.includes('labelExamples')) return { labelExamples: [] }
    return {
      labelQueue: {
        strategy: 'MIXED',
        items: [7, 8].map(id => ({
          id,
          imageUrl: `images/sv_${id}_x.jpg`,
          latitude: 47.5,
          longitude: 19.05,
          streetViewUrl: 'https://example.invalid',
          reason: 'diverse',
          area: 'budapest',
          cellLabels: 0,
          modelRqi: 2,
          modelScore: 2.1,
        })),
        stats: { totalLabelled: 10, labelledToday: 0, eligible: 2, scored: 2 },
      },
    }
  },
  *gqlMutate(options: { variables: unknown }) {
    yield delay(1)
    saved.push(options.variables)
    return { quickLabel: { pointId: 7, rqi: 5, totalLabelled: 11, labelledToday: 1 } }
  },
}))

const { default: reducer, actions } = await import('../slice')
const { default: sagas } = await import('../sagas')
const { QuickLabelView } = await import('./QuickLabelView')

describe('QuickLabelView', () => {
  it('shows one name-first button per scale level and stores the tapped level', async () => {
    window.localStorage.clear()
    const sagaMiddleware = createSagaMiddleware()
    const store = configureStore({
      reducer: combineReducers({ labeling: reducer }),
      middleware: gdm => gdm({ serializableCheck: false }).concat(sagaMiddleware),
    })
    sagaMiddleware.run(function* () {
      yield all(sagas)
    })
    render(
      <Provider store={store}>
        <QuickLabelView onBack={() => {}} />
      </Provider>,
    )
    await act(async () => {
      store.dispatch(actions.enter())
      await new Promise(r => setTimeout(r, 50))
    })

    // The model's guess is not on screen before rating (anchoring bias).
    expect(screen.queryByText(/Modell: /)).toBeNull()

    for (const level of RQI_LEVELS) {
      expect(screen.getByRole('button', { name: level.label_hu })).toBeInTheDocument()
    }
    const worst = RQI_LEVELS[RQI_LEVELS.length - 1]
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: worst.label_hu }))
      await new Promise(r => setTimeout(r, 50))
    })
    expect(saved).toEqual([expect.objectContaining({ input: expect.objectContaining({ pointId: 7, rqi: worst.value }) })])
    // After rating, the previous frame's model guess is revealed.
    expect(screen.getByText(/Modell: Jó/)).toBeInTheDocument()
  })
})
