// The page renders one big button per level of the shared RQI scale (name
// first) and a tap stores that level's value.
import { describe, expect, it, vi } from 'vitest'
import { act, cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import { Provider } from 'react-redux'
import { combineReducers, configureStore } from '@reduxjs/toolkit'
import createSagaMiddleware from 'redux-saga'
import { all, delay } from 'redux-saga/effects'
import { RQI_LEVELS, fromSeverity, rqiValue } from '../../ui'

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
          // the API sends canonical values; the model said Jó (severity 2.1)
          modelRqi: rqiValue('good'),
          modelScore: fromSeverity(2.1),
        })),
        stats: { totalLabelled: 10, labelledToday: 0, eligible: 2, scored: 2, rechecked: 0 },
      },
    }
  },
  *gqlMutate(options: { variables: unknown }) {
    yield delay(1)
    saved.push(options.variables)
    return {
      quickLabel: { pointId: 7, rqi: RQI_LEVELS[RQI_LEVELS.length - 1].value, totalLabelled: 11, labelledToday: 1 },
    }
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
      // longer than the 300 ms double-tap guard
      await new Promise(r => setTimeout(r, 400))
    })

    // The model's guess is not on screen before rating (anchoring bias).
    expect(screen.queryByText(/Modell: /)).toBeNull()

    for (const level of RQI_LEVELS) {
      expect(screen.getByRole('button', { name: level.label_hu })).toBeInTheDocument()
    }
    // The mocked backend sends no examples: every level says so instead of a picture.
    expect(screen.getAllByText('még nincs példa')).toHaveLength(RQI_LEVELS.length)
    fireEvent.click(screen.getByRole('button', { name: 'Skála és példák' }))
    const rubric = within(screen.getByRole('dialog', { name: 'Értékelési skála' }))
    expect(rubric.queryAllByRole('img')).toHaveLength(0)
    expect(rubric.getAllByText('még nincs példa')).toHaveLength(RQI_LEVELS.length)
    for (const level of RQI_LEVELS) {
      expect(rubric.getByText(level.rubric_hu)).toBeInTheDocument()
    }
    fireEvent.click(rubric.getByRole('button', { name: 'Bezárás' }))
    const worst = RQI_LEVELS[RQI_LEVELS.length - 1]
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: worst.label_hu }))
      await new Promise(r => setTimeout(r, 50))
    })
    expect(saved).toEqual([expect.objectContaining({ input: expect.objectContaining({ pointId: 7, rqi: worst.value }) })])
    // After rating, the previous frame's model guess is revealed.
    expect(screen.getByText(/Modell: Jó/)).toBeInTheDocument()
  })

  it('a held key rates nothing and a double tap within 300 ms rates one frame', async () => {
    // The previous test's view must not answer the same window key events.
    cleanup()
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
      await new Promise(r => setTimeout(r, 400))
    })
    const before = saved.length
    const key = String(RQI_LEVELS[0].value)

    // Auto-repeat events of a held key are ignored.
    await act(async () => {
      for (let i = 0; i < 5; i++) fireEvent.keyDown(window, { key, repeat: true })
      await new Promise(r => setTimeout(r, 50))
    })
    expect(saved.length).toBe(before)

    // Two quick presses: the second lands on the next frame, shown for under 300 ms.
    await act(async () => {
      fireEvent.keyDown(window, { key })
    })
    await act(async () => {
      fireEvent.keyDown(window, { key })
      await new Promise(r => setTimeout(r, 50))
    })
    expect(saved.length).toBe(before + 1)
    expect(saved[before]).toEqual(expect.objectContaining({ input: expect.objectContaining({ pointId: 7 }) }))
  })
})
