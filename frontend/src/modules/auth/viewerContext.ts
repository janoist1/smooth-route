import { createContext, useContext } from 'react'

export interface Viewer {
  clerkId: string
  email: string | null
  role: string
}

export interface ViewerState {
  viewer: Viewer | null
  isAdmin: boolean
  loading: boolean
}

export const ViewerContext = createContext<ViewerState>({
  viewer: null,
  isAdmin: false,
  loading: false,
})

export const useViewer = (): ViewerState => useContext(ViewerContext)
