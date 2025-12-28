import { createSelector } from '@reduxjs/toolkit'

// eslint-disable-next-line @typescript-eslint/no-explicit-any
const selectAppDomain = (state: any) => state.app

export const selectAppStarted = createSelector(selectAppDomain, app => app.started)

export const selectRoot = selectAppDomain
