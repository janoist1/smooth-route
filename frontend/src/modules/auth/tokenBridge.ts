// Bridges Clerk's React-only getToken() to non-React modules (Apollo link).
// The Clerk island (ClerkIsland.tsx, loaded after first paint) registers the
// getter; getAuthToken never throws.
//
// Because Clerk now loads lazily, two extra pieces keep signed-in users right:
// - expectSession(): when a Clerk session is likely (session cookie), requests
//   made before the island is up wait for the getter (bounded), as they did
//   when ClerkProvider wrapped the whole app.
// - "settled": false until the island knows the sign-in state and has re-run
//   the active queries; the viewer (and so RequireAdmin) waits for it.

type TokenGetter = () => Promise<string | null>
type Listener = () => void

const WAIT_MS = 10_000

let currentGetter: TokenGetter | null = null
let waitForGetter = false
let getterWaiters: Array<() => void> = []

let settled = true
const settledListeners = new Set<Listener>()

export const setAuthTokenGetter = (getter: TokenGetter | null): void => {
  currentGetter = getter
  if (getter) {
    const waiters = getterWaiters
    getterWaiters = []
    waiters.forEach(resolve => resolve())
  }
}

/** Ask early requests to wait (up to WAIT_MS) for the token getter. */
export const expectSession = (expected: boolean): void => {
  waitForGetter = expected
  if (!expected) {
    const waiters = getterWaiters
    getterWaiters = []
    waiters.forEach(resolve => resolve())
  }
}

const getterReady = (): Promise<void> =>
  new Promise(resolve => {
    const timer = setTimeout(resolve, WAIT_MS)
    getterWaiters.push(() => {
      clearTimeout(timer)
      resolve()
    })
  })

export const getAuthToken = async (): Promise<string | null> => {
  if (!currentGetter && waitForGetter) await getterReady()
  if (!currentGetter) return null
  try {
    return await currentGetter()
  } catch {
    return null
  }
}

/** Is the sign-in state known (and active queries re-run for it)? */
export const isAuthSettled = (): boolean => settled

export const setAuthSettled = (value: boolean): void => {
  if (settled === value) return
  settled = value
  settledListeners.forEach(listener => listener())
}

export const subscribeAuthSettled = (listener: Listener): (() => void) => {
  settledListeners.add(listener)
  return () => settledListeners.delete(listener)
}

/** Clerk keeps `__client_uat` (seconds of the last sign-in, "0" when signed
 * out) on the app's own domain; a non-zero value means a session is likely. */
export const hasClerkSessionCookie = (cookie: string): boolean =>
  /(?:^|;\s*)__client_uat(?:_[^=]*)?=([1-9][0-9]*)/.test(cookie)
