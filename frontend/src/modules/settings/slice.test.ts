import { describe, it, expect } from 'vitest'
import reducer, { actions } from './slice'
import {
  selectCategories,
  selectError,
  selectItems,
  selectLoading,
  selectModelInfo,
  selectSaveLoading,
} from './selectors'
import type { RootState } from '../../store'
import type { SystemSetting } from './types'

const initial = reducer(undefined, { type: '@@INIT' })
type SettingsState = typeof initial

const setting = (key: string, value: string | number, category?: string): SystemSetting => ({ key, value, category })
const root = (settings: SettingsState): RootState => ({ settings }) as unknown as RootState

describe('settings slice — loading the list', () => {
  it('stores the fetched settings', () => {
    let s = reducer({ ...initial, error: 'old' }, { type: actions.fetchSettings.pending.type })
    expect(s).toMatchObject({ loading: true, error: null })

    s = reducer(s, { type: actions.fetchSettings.fulfilled.type, payload: [setting('a', 1)] })
    expect(s).toMatchObject({ loading: false, error: null, items: [setting('a', 1)] })
  })

  it('treats an empty response as an empty list', () => {
    const s = reducer({ ...initial, items: [setting('a', 1)] }, { type: actions.fetchSettings.fulfilled.type, payload: null })
    expect(s.items).toEqual([])
  })

  it('surfaces the failure message, with a fallback', () => {
    const type = actions.fetchSettings.rejected.type
    expect(reducer({ ...initial, loading: true }, { type, error: { message: 'HTTP 503' } })).toMatchObject({
      loading: false,
      error: 'HTTP 503',
    })
    expect(reducer(initial, { type }).error).toBe('Failed to fetch settings')
  })
})

describe('settings slice — saving one setting', () => {
  const loaded: SettingsState = { ...initial, items: [setting('conf', 0.3), setting('rqi_display_source', 'both')] }

  it('replaces the saved setting in place', () => {
    let s = reducer(loaded, { type: actions.updateSetting.pending.type })
    expect(s.saveLoading).toBe(true)

    s = reducer(s, { type: actions.updateSetting.fulfilled.type, payload: setting('conf', 0.5) })
    expect(s.saveLoading).toBe(false)
    expect(s.items).toEqual([setting('conf', 0.5), setting('rqi_display_source', 'both')])
  })

  it('appends a setting the list did not have yet', () => {
    const s = reducer(loaded, { type: actions.updateSetting.fulfilled.type, payload: setting('new_key', 'x') })
    expect(s.items.map(i => i.key)).toEqual(['conf', 'rqi_display_source', 'new_key'])
  })

  it('keeps the list when the save returns nothing', () => {
    const s = reducer({ ...loaded, saveLoading: true }, { type: actions.updateSetting.fulfilled.type, payload: undefined })
    expect(s.saveLoading).toBe(false)
    expect(s.items).toEqual(loaded.items)
  })

  it('surfaces the failure message, with a fallback', () => {
    const type = actions.updateSetting.rejected.type
    expect(reducer({ ...loaded, saveLoading: true }, { type, error: { message: 'read-only' } })).toMatchObject({
      saveLoading: false,
      error: 'read-only',
    })
    expect(reducer(loaded, { type }).error).toBe('Failed to update setting')
  })
})

describe('settings slice — model card', () => {
  it('stores the model info, or null when the backend has none', () => {
    const info = { available: true, qwk: 0.889 }
    let s = reducer(initial, { type: actions.fetchModelInfo.fulfilled.type, payload: info })
    expect(s.modelInfo).toEqual(info)
    s = reducer(s, { type: actions.fetchModelInfo.fulfilled.type, payload: undefined })
    expect(s.modelInfo).toBeNull()
  })
})

describe('settings selectors', () => {
  it('read the plain fields', () => {
    const state = root({
      items: [setting('a', 1)],
      loading: true,
      saveLoading: true,
      error: 'x',
      modelInfo: { available: false },
    })
    expect(selectItems(state)).toEqual([setting('a', 1)])
    expect(selectLoading(state)).toBe(true)
    expect(selectSaveLoading(state)).toBe(true)
    expect(selectError(state)).toBe('x')
    expect(selectModelInfo(state)).toEqual({ available: false })
  })

  it('orders categories by the fixed priority, the rest alphabetically', () => {
    const state = root({
      ...initial,
      items: [
        setting('z', 1, 'Zebra'),
        setting('t', 1, 'Küszöbértékek'),
        setting('g', 1, 'Google Street View'),
        setting('a', 1, 'Alma'),
        setting('m', 1, 'AI & Modell'),
        setting('m2', 1, 'AI & Modell'),
        setting('s', 1, 'Súlyok'),
        setting('tr', 1, 'Tanítás'),
      ],
    })
    expect(selectCategories(state)).toEqual([
      'AI & Modell',
      'Tanítás',
      'Súlyok',
      'Küszöbértékek',
      'Google Street View',
      'Alma',
      'Zebra',
    ])
  })

  it('files settings without a category under "Egyéb"', () => {
    const state = root({ ...initial, items: [setting('x', 1), setting('y', 1, ''), setting('s', 1, 'Súlyok')] })
    expect(selectCategories(state)).toEqual(['Súlyok', 'Egyéb'])
  })
})
