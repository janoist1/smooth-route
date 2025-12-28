import { createAction } from '@reduxjs/toolkit'

// Use a distinct action type string
export const LOCATION_CHANGE = 'ROUTER/LOCATION_CHANGE'

// eslint-disable-next-line @typescript-eslint/no-explicit-any
export const locationChange = createAction<any>(LOCATION_CHANGE)
