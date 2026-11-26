import type { ReactNode } from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, render } from '@testing-library/react'
import ClerkIsland from './ClerkIsland'
import * as tokenBridge from './tokenBridge'

const { getToken, useAuth, refetchQueries } = vi.hoisted(() => ({
  getToken: vi.fn<() => Promise<string | null>>(),
  useAuth: vi.fn(),
  refetchQueries: vi.fn(),
}))

vi.mock('@clerk/clerk-react', () => ({
  ClerkProvider: ({ children }: { children: ReactNode }) => children,
  SignedIn: () => null,
  SignedOut: () => null,
  SignInButton: () => null,
  UserButton: () => null,
  useAuth,
}))
vi.mock('../graphql/client', () => ({ client: { refetchQueries } }))
vi.mock('./config', () => ({ CLERK_PUBLISHABLE_KEY: 'pk_test_mock' }))
vi.mock('./userMenuSlot', () => ({ useUserMenuSlot: () => null }))

beforeEach(() => {
  getToken.mockResolvedValue('jwt-loaded')
  refetchQueries.mockResolvedValue(undefined)
  useAuth.mockReturnValue({ getToken, isLoaded: false, isSignedIn: undefined })
  tokenBridge.expectSession(false)
  tokenBridge.setAuthTokenGetter(null)
})

afterEach(() => {
  cleanup()
  tokenBridge.setAuthTokenGetter(null)
  tokenBridge.setAuthSettled(true)
  vi.restoreAllMocks()
  vi.clearAllMocks()
})

describe('ClerkIsland token registration', () => {
  it('does not register the getter before Clerk is loaded and sends anonymous requests', async () => {
    const register = vi.spyOn(tokenBridge, 'setAuthTokenGetter')
    render(<ClerkIsland />)

    expect(register).not.toHaveBeenCalled()
    expect(await tokenBridge.getAuthToken()).toBeNull()
    expect(getToken).not.toHaveBeenCalled()
  })

  it('registers the getter after Clerk loads and unregisters it on unmount', async () => {
    const register = vi.spyOn(tokenBridge, 'setAuthTokenGetter')
    const { rerender, unmount } = render(<ClerkIsland />)
    useAuth.mockReturnValue({ getToken, isLoaded: true, isSignedIn: false })
    rerender(<ClerkIsland />)

    expect(register).toHaveBeenCalledWith(expect.any(Function))
    expect(await tokenBridge.getAuthToken()).toBe('jwt-loaded')
    unmount()
    expect(register).toHaveBeenLastCalledWith(null)
    expect(await tokenBridge.getAuthToken()).toBeNull()
  })
})
