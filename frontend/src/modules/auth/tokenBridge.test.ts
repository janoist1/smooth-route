import { describe, it, expect, afterEach } from 'vitest'
import { getAuthToken, setAuthTokenGetter } from './tokenBridge'

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
