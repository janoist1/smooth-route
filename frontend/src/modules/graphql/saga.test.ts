import { describe, it, expect, vi, beforeEach } from 'vitest'
import { runSaga } from 'redux-saga'
import type { Saga } from 'redux-saga'
import type { TypedDocumentNode } from '@graphql-typed-document-node/core'

const { query, mutate } = vi.hoisted(() => ({ query: vi.fn(), mutate: vi.fn() }))
vi.mock('./client', () => ({ client: { query, mutate } }))

import { gqlMutate, gqlQuery, gqlQueryResult } from './saga'

type Data = { road: { id: number } }
type Vars = { id: number }

const DOC = { kind: 'Document', definitions: [] } as unknown as TypedDocumentNode<Data, Vars>

const run = <T>(saga: () => Generator<unknown, T, unknown>): Promise<T> =>
  runSaga({ dispatch: () => undefined, getState: () => ({}) }, saga as Saga).toPromise() as Promise<T>

beforeEach(() => {
  query.mockReset()
  mutate.mockReset()
})

describe('gqlQueryResult', () => {
  it('passes the options to the Apollo client and returns its raw result', async () => {
    const result = { data: { road: { id: 1 } }, error: undefined }
    query.mockResolvedValue(result)

    const options = { query: DOC, variables: { id: 1 }, fetchPolicy: 'network-only' as const }
    await expect(run(() => gqlQueryResult(options))).resolves.toBe(result)
    expect(query).toHaveBeenCalledTimes(1)
    expect(query).toHaveBeenCalledWith(options)
  })

  it('returns an errored result as-is (data undefined) instead of throwing', async () => {
    const error = new Error('Cannot query field "roadSegments"')
    query.mockResolvedValue({ data: undefined, error })

    await expect(run(() => gqlQueryResult({ query: DOC, variables: { id: 1 } }))).resolves.toEqual({
      data: undefined,
      error,
    })
  })
})

describe('gqlQuery', () => {
  it('returns the data', async () => {
    query.mockResolvedValue({ data: { road: { id: 7 } } })
    await expect(run(() => gqlQuery({ query: DOC, variables: { id: 7 } }))).resolves.toEqual({ road: { id: 7 } })
  })

  it('throws the Apollo error when the query returned no data', async () => {
    const error = new Error('Unauthorized')
    query.mockResolvedValue({ data: undefined, error })
    await expect(run(() => gqlQuery({ query: DOC, variables: { id: 7 } }))).rejects.toBe(error)
  })

  it('throws a generic error when there is neither data nor an error', async () => {
    query.mockResolvedValue({ data: null })
    await expect(run(() => gqlQuery({ query: DOC, variables: { id: 7 } }))).rejects.toThrow(
      'GraphQL query returned no data',
    )
  })

  it('propagates a network failure', async () => {
    query.mockRejectedValue(new Error('Failed to fetch'))
    await expect(run(() => gqlQuery({ query: DOC, variables: { id: 7 } }))).rejects.toThrow('Failed to fetch')
  })
})

describe('gqlMutate', () => {
  it('passes the options to the Apollo client and returns the mutation data', async () => {
    mutate.mockResolvedValue({ data: { road: { id: 3 } } })

    const options = { mutation: DOC, variables: { id: 3 } }
    await expect(run(() => gqlMutate(options))).resolves.toEqual({ road: { id: 3 } })
    expect(mutate).toHaveBeenCalledWith(options)
    expect(query).not.toHaveBeenCalled()
  })

  it('propagates a mutation error', async () => {
    mutate.mockRejectedValue(new Error('Forbidden'))
    await expect(run(() => gqlMutate({ mutation: DOC, variables: { id: 3 } }))).rejects.toThrow('Forbidden')
  })
})
