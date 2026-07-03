// Bridges Clerk's React-only getToken() to non-React modules (Apollo link).
// AuthProvider registers the getter; getAuthToken never throws.

type TokenGetter = () => Promise<string | null>

let currentGetter: TokenGetter | null = null

export const setAuthTokenGetter = (getter: TokenGetter | null): void => {
  currentGetter = getter
}

export const getAuthToken = async (): Promise<string | null> => {
  if (!currentGetter) return null
  try {
    return await currentGetter()
  } catch {
    return null
  }
}
