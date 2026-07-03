import React from 'react'
import { Navigate } from 'react-router-dom'
import { useViewer } from './viewerContext'

/** Route guard for admin-only pages. UX only — the backend enforces the same
 * rule on every query/mutation these pages fire. */
export const RequireAdmin: React.FC<{ children: React.ReactElement }> = ({ children }) => {
  const { isAdmin, loading } = useViewer()
  if (loading) return null
  if (!isAdmin) return <Navigate to="/" replace />
  return children
}
