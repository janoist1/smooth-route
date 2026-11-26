import React, { useCallback } from 'react'
import { authEnabled } from './config'
import { setUserMenuSlot } from './userMenuSlot'

/** Slot for the sign-in pill / Clerk user button in the floating nav row. The
 * lazily loaded Clerk island portals the button in here (ClerkIsland.tsx);
 * until it arrives the slot is empty, as Clerk's <SignedOut> was before load. */
export const UserMenu: React.FC = () => {
  const ref = useCallback((el: HTMLDivElement | null) => setUserMenuSlot(el), [])
  if (!authEnabled) return null
  return <div ref={ref} style={{ pointerEvents: 'auto', display: 'flex', alignItems: 'center' }} />
}
