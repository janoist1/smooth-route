import { configureStore, combineReducers } from '@reduxjs/toolkit'
import createSagaMiddleware from 'redux-saga'
import { all } from 'redux-saga/effects'

// Reducers
import { reducer as mapReducer, sagas as mapSagas } from './modules/map'
import { reducer as trainingReducer, sagas as trainingSagas } from './modules/training'
import { reducer as settingsReducer, sagas as settingsSagas } from './modules/settings'
import { reducer as appReducer } from './modules/app'
import { reducer as apiReducer, sagas as apiSagas } from './modules/api'

// Sagas
import globalSagas from './sagas'

function* rootSaga() {
  const allSagas = [...mapSagas, ...trainingSagas, ...settingsSagas, ...globalSagas, ...apiSagas]
  yield all(allSagas)
}

const rootReducer = combineReducers({
  map: mapReducer,
  training: trainingReducer,
  settings: settingsReducer,
  app: appReducer,
  api: apiReducer,
})

const sagaMiddleware = createSagaMiddleware()

const getPreloadedState = () => {
  if (typeof window === 'undefined') return undefined

  const params = new URLSearchParams(window.location.search)
  const lat = params.get('lat')
  const lng = params.get('lng')
  const z = params.get('z')

  if (lat && lng && z) {
    return {
      map: {
        points: [],
        loading: false,
        error: null,
        selectedPointId: null,
        selectedPointDetail: null,
        loadingDetail: false,
        viewport: {
          center: [parseFloat(lat), parseFloat(lng)] as [number, number],
          zoom: parseInt(z, 10),
        },
      },
    }
  }
  return undefined
}

export const store = configureStore({
  reducer: rootReducer,
  preloadedState: getPreloadedState(),
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
          payload: `<<LARGE_ARRAY_SANITIZED: ${action.payload.length} items>>`,
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
            points: `<<LARGE_POINT_ARRAY: ${state.map.points.length} items>>`,
          },
        }
      }
      return state
    },
  },
})

sagaMiddleware.run(rootSaga)

export type AppDispatch = typeof store.dispatch
export type RootState = ReturnType<typeof rootReducer>
