import type { ReactNode } from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { act, cleanup, render } from '@testing-library/react'
import ClerkIsland from './ClerkIsland'
import * as tokenBridge from './tokenBridge'

const { getToken, useAuth, refetchQueries, dispatch } = vi.hoisted(() => ({
  getToken: vi.fn<() => Promise<string | null>>(),
  useAuth: vi.fn(),
  refetchQueries: vi.fn(),
  dispatch: vi.fn(),
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
vi.mock('react-redux', () => ({ useDispatch: () => dispatch }))

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
  tokenBridge.cancelAuthFallback()
  vi.useRealTimers()
  vi.restoreAllMocks()
  vi.clearAllMocks()
})

describe('ClerkIsland token registration', () => {
  it('cancels the anonymous fallback on mount and re-emits the route after the first signed-in answer', async () => {
    vi.useFakeTimers()
    tokenBridge.setAuthSettled(false)
    tokenBridge.startAuthFallback()
    expect(vi.getTimerCount()).toBe(1)
    const { rerender } = render(<ClerkIsland />)
    expect(vi.getTimerCount()).toBe(0)
    await vi.advanceTimersByTimeAsync(15_000)
    expect(tokenBridge.isAuthSettled()).toBe(false)
    expect(dispatch).not.toHaveBeenCalled()

    let finish!: () => void
    refetchQueries.mockReturnValue(new Promise<void>(resolve => { finish = resolve }))
    useAuth.mockReturnValue({ getToken, isLoaded: true, isSignedIn: true })
    rerender(<ClerkIsland />)
    expect(tokenBridge.isAuthSettled()).toBe(false)
    expect(dispatch).not.toHaveBeenCalled()
    await act(async () => { finish() })
    expect(tokenBridge.isAuthSettled()).toBe(true)
    expect(dispatch).toHaveBeenCalledExactlyOnceWith({
      type: 'ROUTER/LOCATION_CHANGE',
      payload: { pathname: window.location.pathname, search: window.location.search },
    })
  })
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
