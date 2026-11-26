import { describe, it, expect, afterEach, vi } from 'vitest'
import {
  expectSession,
  getAuthToken,
  hasClerkSessionCookie,
  isAuthSettled,
  setAuthSettled,
  setAuthTokenGetter,
  subscribeAuthSettled,
} from './tokenBridge'

afterEach(() => setAuthTokenGetter(null))

describe('tokenBridge', () => {
  it('returns null when no getter is registered', async () => {
    expect(await getAuthToken()).toBeNull()
  })

  it('returns the token from the registered getter', async () => {
    setAuthTokenGetter(async () => 'jwt-abc')
    expect(await getAuthToken()).toBe('jwt-abc')
  })

  it('returns null after the getter is unregistered', async () => {
    setAuthTokenGetter(async () => 'jwt-abc')
    setAuthTokenGetter(null)
    expect(await getAuthToken()).toBeNull()
  })

  it('swallows getter errors and falls back to anonymous', async () => {
    setAuthTokenGetter(async () => {
      throw new Error('clerk not loaded')
    })
    expect(await getAuthToken()).toBeNull()
  })

  it('gives up on a hung getter at 3 s and goes anonymous', async () => {
    vi.useFakeTimers()
    try {
      // A blocked Clerk host: getToken() never settles.
      setAuthTokenGetter(() => new Promise<string | null>(() => {}))
      let result: string | null | undefined
      void getAuthToken().then(token => {
        result = token
      })
      await vi.advanceTimersByTimeAsync(2_999)
      expect(result).toBeUndefined()
      await vi.advanceTimersByTimeAsync(1)
      expect(result).toBeNull()
      expect(vi.getTimerCount()).toBe(0)
    } finally {
      vi.useRealTimers()
    }
  })

  it('does not leave the timeout timer behind when the getter answers', async () => {
    vi.useFakeTimers()
    try {
      setAuthTokenGetter(async () => 'jwt-fast')
      expect(await getAuthToken()).toBe('jwt-fast')
      expect(vi.getTimerCount()).toBe(0)
    } finally {
      vi.useRealTimers()
    }
  })
})

describe('tokenBridge — lazily loaded Clerk', () => {
  afterEach(() => {
    expectSession(false)
    setAuthSettled(true)
  })

  it('waits for the getter when a session is expected', async () => {
    expectSession(true)
    const pending = getAuthToken()
    setAuthTokenGetter(async () => 'jwt-late')
    expect(await pending).toBe('jwt-late')
  })

  it('stops waiting when the session turns out not to exist', async () => {
    expectSession(true)
    const pending = getAuthToken()
    expectSession(false)
    expect(await pending).toBeNull()
  })

  it('does not wait for anonymous visitors', async () => {
    expect(await getAuthToken()).toBeNull()
  })

  it('waits up to 10 s for Clerk readiness when a session is expected', async () => {
    vi.useFakeTimers()
    try {
      expectSession(true)
      const result = vi.fn()
      void getAuthToken().then(result)
      await vi.advanceTimersByTimeAsync(3_000)
      expect(result).not.toHaveBeenCalled()
      await vi.advanceTimersByTimeAsync(6_999)
      expect(result).not.toHaveBeenCalled()
      setAuthTokenGetter(async () => 'jwt-slow-connection')
      await vi.advanceTimersByTimeAsync(0)
      expect(result).toHaveBeenCalledWith('jwt-slow-connection')
      expect(vi.getTimerCount()).toBe(0)
    } finally {
      vi.useRealTimers()
    }
  })

  it('goes anonymous at 10 s, releases concurrent waits and never waits again after readiness times out', async () => {
    vi.useFakeTimers()
    try {
      expectSession(true)
      const result = vi.fn()
      void getAuthToken().then(result)
      await vi.advanceTimersByTimeAsync(2_000)
      const concurrent = vi.fn()
      void getAuthToken().then(concurrent)
      await vi.advanceTimersByTimeAsync(7_999)
      expect(result).not.toHaveBeenCalled()
      expect(concurrent).not.toHaveBeenCalled()
      await vi.advanceTimersByTimeAsync(1)
      expect(result).toHaveBeenCalledWith(null)
      expect(concurrent).toHaveBeenCalledWith(null)
      expect(vi.getTimerCount()).toBe(0)

      const later = vi.fn()
      void getAuthToken().then(later)
      await vi.advanceTimersByTimeAsync(0)
      expect(later).toHaveBeenCalledWith(null)
      expect(vi.getTimerCount()).toBe(0)
    } finally {
      vi.useRealTimers()
    }
  })

  it('gives a late Clerk getter its own 3 s timeout', async () => {
    vi.useFakeTimers()
    try {
      expectSession(true)
      const result = vi.fn()
      void getAuthToken().then(result)
      await vi.advanceTimersByTimeAsync(9_000)
      setAuthTokenGetter(() => new Promise<string | null>(() => {}))
      await vi.advanceTimersByTimeAsync(2_999)
      expect(result).not.toHaveBeenCalled()
      await vi.advanceTimersByTimeAsync(1)
      expect(result).toHaveBeenCalledWith(null)
      expect(vi.getTimerCount()).toBe(0)
    } finally {
      vi.useRealTimers()
    }
  })

  it('notifies settled-state listeners', () => {
    const seen: boolean[] = []
    const off = subscribeAuthSettled(() => seen.push(isAuthSettled()))
    setAuthSettled(false)
    setAuthSettled(true)
    off()
    expect(seen).toEqual([false, true])
  })

  it('reads the Clerk session cookie', () => {
    expect(hasClerkSessionCookie('a=1; __client_uat=1732600000')).toBe(true)
    expect(hasClerkSessionCookie('__client_uat_Ab12=1732600000; b=2')).toBe(true)
    expect(hasClerkSessionCookie('__client_uat=0')).toBe(false)
    expect(hasClerkSessionCookie('x=1')).toBe(false)
  })
})
