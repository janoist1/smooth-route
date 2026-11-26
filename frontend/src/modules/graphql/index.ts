// Service Module: GraphQL
import { gql as graphqlTag } from 'graphql-tag'
import type { gql as generatedGql } from './generated/gql'

export { client } from './client'
export { gqlQuery, gqlQueryResult, gqlMutate } from './saga'
// Export generated types
export * from './generated'

/**
 * `gql` keeps graphql-tag's runtime (parse + cache), but is typed with the
 * codegen overloads: `gql('<exact source>')` resolves to the generated
 * TypedDocumentNode, which Apollo Client 4 needs to infer result/variable
 * types. A source string codegen has not seen resolves to `unknown`, so
 * typechecking fails until `npm run codegen` is re-run; tagged-template use
 * still yields a plain DocumentNode.
 */
export const gql = graphqlTag as unknown as typeof generatedGql & typeof graphqlTag
