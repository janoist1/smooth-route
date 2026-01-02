import { configureStore, combineReducers } from '@reduxjs/toolkit'
import createSagaMiddleware from 'redux-saga'
import { all } from 'redux-saga/effects'

// Reducers
import { reducer as mapReducer, sagas as mapSagas } from './modules/map'
import { reducer as trainingReducer, sagas as trainingSagas } from './modules/training'
import { reducer as appReducer } from './modules/app'

// Sagas
import globalSagas from './sagas'

function* rootSaga() {
  yield all([...mapSagas, ...trainingSagas, ...globalSagas])
}

const rootReducer = combineReducers({
  map: mapReducer,
  training: trainingReducer,
  app: appReducer,
})

const sagaMiddleware = createSagaMiddleware()

export const store = configureStore({
  reducer: rootReducer,
  middleware: getDefaultMiddleware =>
    getDefaultMiddleware({ serializableCheck: false }).concat(sagaMiddleware),
  devTools: {
    name: 'Smooth Route',
    trace: true,
    traceLimit: 25,
    // Sanitize actions to prevent massive payloads from logging lagging DevTools
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    actionSanitizer: (action: any) => {
      if (action.payload && Array.isArray(action.payload) && action.payload.length > 50) {
        return {
          ...action,
          payload: `<<LARGE_ARRAY_SANITIZED: ${action.payload.length} items>>`
        }
      }
      return action
    },
    // Sanitize state to avoid choking on massive arrays
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    stateSanitizer: (state: any) => {
      if (state.map && state.map.points && state.map.points.length > 50) {
        return {
          ...state,
          map: {
            ...state.map,
            points: `<<LARGE_POINT_ARRAY: ${state.map.points.length} items>>`
          }
        }
      }
      return state
    }
  },
})

sagaMiddleware.run(rootSaga)

export type AppDispatch = typeof store.dispatch
export type RootState = ReturnType<typeof rootReducer>
