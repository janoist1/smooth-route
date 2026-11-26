import type { LabelingState } from './types'

type WithLabeling = { labeling: LabelingState }

export const selectRoot = (state: WithLabeling) => state.labeling
export const selectCurrent = (state: WithLabeling) => state.labeling.queue[0] ?? null
export const selectQueue = (state: WithLabeling) => state.labeling.queue
export const selectHistory = (state: WithLabeling) => state.labeling.history
