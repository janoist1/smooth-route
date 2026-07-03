import { createSelector } from '@reduxjs/toolkit'
import type { RootState } from '../../store'
import type { RqiDisplaySource } from '../ui'

export const selectRoot = (state: RootState) => state.settings

export const selectItems = createSelector([selectRoot], settings => settings.items)

/** Typed accessor for the `rqi_display_source` setting (defaults to 'both'). */
export const selectRqiDisplaySource = createSelector([selectItems], (items): RqiDisplaySource => {
  const raw = items.find(item => item.key === 'rqi_display_source')?.value
  return raw === 'yolo' || raw === 'dino' ? raw : 'both'
})

export const selectModelInfo = createSelector([selectRoot], settings => settings.modelInfo)

export const selectLoading = createSelector([selectRoot], settings => settings.loading)

export const selectSaveLoading = createSelector([selectRoot], settings => settings.saveLoading)

export const selectError = createSelector([selectRoot], settings => settings.error)

export const selectCategories = createSelector([selectItems], items => {
  const cats = Array.from(new Set(items.map(item => item.category || 'Egyéb')))
  const priority = ['AI & Modell', 'Tanítás', 'Súlyok', 'Küszöbértékek', 'Google Street View']

  return cats.sort((a, b) => {
    const indexA = priority.indexOf(a)
    const indexB = priority.indexOf(b)
    if (indexA !== -1 && indexB !== -1) return indexA - indexB
    if (indexA !== -1) return -1
    if (indexB !== -1) return 1
    return a.localeCompare(b)
  })
})
