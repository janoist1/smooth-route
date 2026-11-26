// Feature module: quick-rate labelling screen ("Gyors címkézés", /training/quick).
// Backend: labelQueue / labelExamples / quickLabel / undoQuickLabel (admin-only).
import reducer from './slice'
import sagas from './sagas'
import { actions } from './slice'
import * as selectors from './selectors'

export * from './hooks'
export * from './components'
export * from './types'
export { reducer, sagas, actions, selectors }
