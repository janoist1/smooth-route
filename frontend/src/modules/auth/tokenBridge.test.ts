import { describe, it, expect, afterEach } from 'vitest'
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
