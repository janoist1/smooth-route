import { createSelector } from '@reduxjs/toolkit'
import type { RootState } from '../../store'

const selectTrainingDomain = (state: RootState) => state.training

export const selectImage = createSelector(selectTrainingDomain, training => ({
  url: training.imageUrl,
  loading: training.loading,
  error: training.error,
}))

export const selectAnnotations = createSelector(
  selectTrainingDomain,
  training => training.annotations,
)

export const selectTool = createSelector(selectTrainingDomain, training => training.selectedTool)

export const selectTrainingState = selectTrainingDomain
