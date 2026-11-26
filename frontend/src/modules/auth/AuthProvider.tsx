import React, { Suspense, lazy } from 'react'
import { authEnabled } from './config'
import { expectSession, hasClerkSessionCookie, setAuthSettled } from './tokenBridge'

// Clerk (~90 kB) is not in the first download: the island loads in its own
// chunk right after the app starts, beside the app rather than around it.
const ClerkIsland = lazy(() => import('./ClerkIsland'))

if (authEnabled && typeof document !== 'undefined') {
  // Until the island knows the sign-in state, the viewer is "loading"; a
  // likely-signed-in visitor's early requests wait for the token.
  setAuthSettled(false)
  expectSession(hasClerkSessionCookie(document.cookie))
  // If Clerk never loads (blocked CDN, offline), stop waiting: anonymous.
  setTimeout(() => {
    expectSession(false)
    setAuthSettled(true)
  }, 15_000)
}

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => (
  <>
    {children}
    {authEnabled && (
      <Suspense fallback={null}>
        <ClerkIsland />
      </Suspense>
    )}
  </>
)
