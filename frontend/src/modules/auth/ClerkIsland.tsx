// Everything that needs Clerk, in one lazily loaded chunk (see AuthProvider).
// It does not wrap the app: only the token bridge and the nav's sign-in /
// user button use Clerk, so the island mounts beside the app and portals the
// button into the nav's slot. The app tree never remounts when Clerk arrives.
import React, { useEffect, useRef } from 'react'
import { createPortal } from 'react-dom'
import { ClerkProvider, SignedIn, SignedOut, SignInButton, UserButton, useAuth } from '@clerk/clerk-react'
import { LogIn } from 'lucide-react'
import { client } from '../graphql/client'
import { CLERK_PUBLISHABLE_KEY } from './config'
import { expectSession, setAuthSettled, setAuthTokenGetter } from './tokenBridge'
import { useUserMenuSlot } from './userMenuSlot'

/** Registers Clerk's getToken for the Apollo auth link; once the sign-in state
 * is known (and whenever it flips) re-runs the active queries, then marks auth
 * as settled so the viewer / admin guard can decide. */
const TokenBridge: React.FC = () => {
  const { getToken, isLoaded, isSignedIn } = useAuth()

  useEffect(() => {
    if (!isLoaded) return
    setAuthTokenGetter(() => getToken())
    return () => setAuthTokenGetter(null)
  }, [getToken, isLoaded])

  const known = useRef<boolean | undefined>(undefined)
  useEffect(() => {
    if (!isLoaded) return
    const signedIn = Boolean(isSignedIn)
    const first = known.current === undefined
    const changed = known.current !== signedIn
    known.current = signedIn
    expectSession(false)
    if (!changed) return
    // First answer: queries sent before the island loaded went out anonymous
    // unless they waited for the token; re-run them only if we are signed in.
    if (first && !signedIn) {
      setAuthSettled(true)
      return
    }
    setAuthSettled(false)
    void client.refetchQueries({ include: 'active' }).finally(() => setAuthSettled(true))
  }, [isLoaded, isSignedIn])

  return null
}

const ClerkUserMenu: React.FC = () => (
  <>
    <SignedOut>
      <SignInButton mode="modal">
        <button
          className="fnav-btn"
          aria-label="Sign in"
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '8px',
            padding: '10px 16px',
            borderRadius: '9999px',
            border: '1px solid rgba(255, 255, 255, 0.1)',
            background: 'rgba(0, 0, 0, 0.4)',
            color: '#d1d5db',
            backdropFilter: 'blur(12px)',
            cursor: 'pointer',
            fontSize: '0.875rem',
            fontWeight: 500,
          }}>
          <LogIn size={20} />
          {/* Hidden on phones by FloatingNavBar's .fnav-label rule. */}
          <span className="fnav-label">Sign in</span>
        </button>
      </SignInButton>
    </SignedOut>
    <SignedIn>
      <UserButton />
    </SignedIn>
  </>
)

const ClerkIsland: React.FC = () => {
  const slot = useUserMenuSlot()
  return (
    <ClerkProvider publishableKey={CLERK_PUBLISHABLE_KEY} afterSignOutUrl="/">
      <TokenBridge />
      {slot && createPortal(<ClerkUserMenu />, slot)}
    </ClerkProvider>
  )
}

export default ClerkIsland
