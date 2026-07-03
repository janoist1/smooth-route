import type { PayloadAction } from '@reduxjs/toolkit'
import { createSlice } from '@reduxjs/toolkit'
import { createSagaAction } from 'saga-toolkit'
import type { SystemSetting } from './types'

interface SettingsState {
  items: SystemSetting[]
  loading: boolean
  error: string | null
  saveLoading: boolean
}

const initialState: SettingsState = {
  items: [],
  loading: false,
  error: null,
  saveLoading: false,
}

export const fetchSettings = createSagaAction<SystemSetting[]>('settings/fetchSettings')
export const updateSetting = createSagaAction<SystemSetting, { key: string; value: unknown }>(
  'settings/updateSetting',
)

const settingsSlice = createSlice({
  name: 'settings',
  initialState,
  reducers: {},
  extraReducers: builder => {
    // fetchSettings
    builder.addCase(fetchSettings.pending, state => {
      state.loading = true
      state.error = null
    })
    builder.addCase(fetchSettings.fulfilled, (state, action: PayloadAction<SystemSetting[]>) => {
      state.loading = false
      state.items = action.payload || []
      state.error = null
    })
    builder.addCase(fetchSettings.rejected, (state, action) => {
      state.loading = false
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const err = (action as any).error
      state.error = err?.message || 'Failed to fetch settings'
    })

    // updateSetting
    builder.addCase(updateSetting.pending, state => {
      state.saveLoading = true
      state.error = null
    })
    builder.addCase(updateSetting.fulfilled, (state, action: PayloadAction<SystemSetting>) => {
      state.saveLoading = false
      const updated = action.payload
      if (updated) {
        const index = state.items.findIndex(s => s.key === updated.key)
        if (index !== -1) {
          state.items[index] = updated
        } else {
          state.items.push(updated)
        }
      }
    })
    builder.addCase(updateSetting.rejected, (state, action) => {
      state.saveLoading = false
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const err = (action as any).error
      state.error = err?.message || 'Failed to update setting'
    })

  },
})

export const actions = {
  ...settingsSlice.actions,
  fetchSettings,
  updateSetting,
}

// Export nothing from actions manually
export default settingsSlice.reducer
