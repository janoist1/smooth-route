import React, { useEffect, useRef } from 'react'
import { ClerkProvider, useAuth } from '@clerk/clerk-react'
import { client } from '../graphql/client'
import { CLERK_PUBLISHABLE_KEY, authEnabled } from './config'
import { setAuthTokenGetter } from './tokenBridge'

/** Registers Clerk's getToken for the Apollo auth link and re-runs active
 * queries when the sign-in state flips (viewer/role changes with it). */
const TokenBridge: React.FC = () => {
  const { getToken, isSignedIn } = useAuth()

  useEffect(() => {
    setAuthTokenGetter(() => getToken())
    return () => setAuthTokenGetter(null)
  }, [getToken])

  const firstRender = useRef(true)
  useEffect(() => {
    if (firstRender.current) {
      firstRender.current = false
      return
    }
    void client.refetchQueries({ include: 'active' })
  }, [isSignedIn])

  return null
}

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  if (!authEnabled) {
    return <>{children}</>
  }
  return (
    <ClerkProvider publishableKey={CLERK_PUBLISHABLE_KEY} afterSignOutUrl="/">
      <TokenBridge />
      {children}
    </ClerkProvider>
  )
}
