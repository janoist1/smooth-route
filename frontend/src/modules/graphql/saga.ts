import { call } from 'redux-saga/effects'
import type { ApolloClient, OperationVariables } from '@apollo/client'
import type { TypedDocumentNode } from '@graphql-typed-document-node/core'
import { client } from './client'

// Typed wrappers for Apollo calls inside sagas. `call([client, client.query], …)`
// loses Apollo Client 4's TypedDocumentNode inference (generic, overloaded
// method), so the call goes through these plain functions instead.

type QueryOptions<TData, TVariables extends OperationVariables> = {
  query: TypedDocumentNode<TData, TVariables>
  fetchPolicy?: ApolloClient.QueryOptions['fetchPolicy']
} & (Record<never, never> extends TVariables
  ? { variables?: TVariables }
  : { variables: TVariables })

type MutateOptions<TData, TVariables extends OperationVariables> = {
  mutation: TypedDocumentNode<TData, TVariables>
} & (Record<never, never> extends TVariables
  ? { variables?: TVariables }
  : { variables: TVariables })

// Inside these generic wrappers TypeScript cannot resolve Apollo's deferred
// option types, so the options are cast once here; the public helpers below
// (and therefore every call site) stay fully typed by the document.
function runQuery<TData, TVariables extends OperationVariables>(
  options: QueryOptions<TData, TVariables>,
) {
  return client.query(options as never) as unknown as Promise<ApolloClient.QueryResult<TData>>
}

function runMutate<TData, TVariables extends OperationVariables>(
  options: MutateOptions<TData, TVariables>,
) {
  return client.mutate(options as never) as unknown as Promise<ApolloClient.MutateResult<TData>>
}

/** Query result as Apollo returns it: `data` is undefined when the query errored (errorPolicy 'all'). */
export function* gqlQueryResult<TData, TVariables extends OperationVariables>(
  options: QueryOptions<TData, TVariables>,
) {
  const result = (yield call(runQuery<TData, TVariables>, options)) as Awaited<
    ReturnType<typeof runQuery<TData, TVariables>>
  >
  return result
}

/** Query data; throws the Apollo error (or a generic one) instead of returning undefined. */
export function* gqlQuery<TData, TVariables extends OperationVariables>(
  options: QueryOptions<TData, TVariables>,
) {
  const { data, error } = yield* gqlQueryResult(options)
  if (data === undefined || data === null) throw error ?? new Error('GraphQL query returned no data')
  return data as TData
}

/** Mutation data (client default errorPolicy 'none' already throws on errors). */
export function* gqlMutate<TData, TVariables extends OperationVariables>(
  options: MutateOptions<TData, TVariables>,
) {
  const result = (yield call(runMutate<TData, TVariables>, options)) as Awaited<
    ReturnType<typeof runMutate<TData, TVariables>>
  >
  return result.data as TData
}
