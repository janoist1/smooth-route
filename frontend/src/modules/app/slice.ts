import { createSlice } from '@reduxjs/toolkit'
import { createSagaAction } from 'saga-toolkit'

export const start = createSagaAction<void, void>('app/start')

interface AppState {
  started: boolean
}

const initialState: AppState = {
  started: false,
}

const appSlice = createSlice({
  name: 'app',
  initialState,
  reducers: {},
  extraReducers: builder => {
    builder.addCase(start.fulfilled, state => {
      state.started = true
    })
  },
})

export const actions = { ...appSlice.actions, start }
export const reducer = appSlice.reducer
