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
export const applyPreset = createSagaAction<SystemSetting[], Record<string, unknown>>(
  'settings/applyPreset',
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

    // applyPreset
    builder.addCase(applyPreset.pending, state => {
      state.saveLoading = true
      state.error = null
    })
    builder.addCase(applyPreset.fulfilled, (state, action: PayloadAction<SystemSetting[]>) => {
      state.saveLoading = false
      const updatedList = action.payload
      if (updatedList) {
        updatedList.forEach((updated: SystemSetting) => {
          const index = state.items.findIndex(s => s.key === updated.key)
          if (index !== -1) {
            state.items[index] = updated
          } else {
            state.items.push(updated)
          }
        })
      }
    })
    builder.addCase(applyPreset.rejected, (state, action) => {
      state.saveLoading = false
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const err = (action as any).error
      state.error = err?.message || 'Failed to apply preset'
    })
  },
})

export const actions = {
  ...settingsSlice.actions,
  fetchSettings,
  updateSetting,
  applyPreset,
}

// Export nothing from actions manually
export default settingsSlice.reducer
