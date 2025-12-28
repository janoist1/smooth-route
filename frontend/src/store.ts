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
  yield all([
    ...mapSagas,
    ...trainingSagas,
    ...globalSagas,
  ])
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
  devTools: import.meta.env.DEV,
})

sagaMiddleware.run(rootSaga)

export type AppDispatch = typeof store.dispatch
export type RootState = ReturnType<typeof rootReducer>
