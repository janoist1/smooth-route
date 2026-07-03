import React from 'react'
import { SignedIn, SignedOut, SignInButton, UserButton } from '@clerk/clerk-react'
import { LogIn } from 'lucide-react'
import { authEnabled } from './config'

/** Sign-in pill / Clerk user button, styled to sit in the floating nav row. */
export const UserMenu: React.FC = () => {
  if (!authEnabled) return null

  return (
    <div style={{ pointerEvents: 'auto', display: 'flex', alignItems: 'center' }}>
      <SignedOut>
        <SignInButton mode="modal">
          <button
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
            Sign in
          </button>
        </SignInButton>
      </SignedOut>
      <SignedIn>
        <UserButton />
      </SignedIn>
    </div>
  )
}
