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

export const client = new ApolloClient({
  link: ApolloLink.from([authLink, new HttpLink({ uri: '/graphql' })]),
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
