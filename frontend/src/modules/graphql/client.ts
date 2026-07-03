import { ApolloClient, InMemoryCache, HttpLink, ApolloLink } from '@apollo/client'
import { SetContextLink } from '@apollo/client/link/context'
import { getAuthToken } from '../auth/tokenBridge'

// Attaches the Clerk session token when one is available; anonymous otherwise.
const authLink = new SetContextLink(async prevContext => {
  const token = await getAuthToken()
  if (!token) return prevContext
  return {
    ...prevContext,
    headers: { ...prevContext.headers, authorization: `Bearer ${token}` },
  }
})

// Dev: empty → relative "/graphql" (Vite proxy to :8000). Prod: the read-API
// origin, e.g. https://api.simaut.hu (frontend and API are separate deploys).
const API_URL = import.meta.env.VITE_API_URL ?? ''

export const client = new ApolloClient({
  link: ApolloLink.from([authLink, new HttpLink({ uri: `${API_URL}/graphql` })]),
  cache: new InMemoryCache(),
  defaultOptions: {
    watchQuery: {
      fetchPolicy: 'no-cache',
      errorPolicy: 'ignore',
    },
    query: {
      fetchPolicy: 'no-cache',
      errorPolicy: 'all',
    },
  },
})
