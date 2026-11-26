import React from 'react'
import { gql } from '../graphql'
import { useQuery } from '@apollo/client/react'
import { ViewerContext } from './viewerContext'

// Role comes from our users table (via the me query), not from Clerk:
// admins are promoted in the DB, so the token alone never grants admin UI.
const VIEWER_QUERY = gql(`
  query Viewer {
    me {
      clerkId
      email
      role
    }
  }
`)

export const ViewerProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const { data, loading } = useQuery(VIEWER_QUERY, {
    fetchPolicy: 'no-cache',
    errorPolicy: 'all',
  })
  const viewer = data?.me ?? null
  return (
    <ViewerContext.Provider value={{ viewer, isAdmin: viewer?.role === 'admin', loading }}>
      {children}
    </ViewerContext.Provider>
  )
}
