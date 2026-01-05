import { createSelector } from '@reduxjs/toolkit'
import type { RootState } from '../../store'

export const selectRoot = (state: RootState) => state.settings

export const selectItems = createSelector([selectRoot], settings => settings.items)

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
