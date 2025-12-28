/* eslint-disable @typescript-eslint/no-explicit-any */
export interface TypedDocumentNode<
  Result = { [key: string]: any },
  Variables = { [key: string]: any },
> {
  kind: 'Document'
  __apiType?: (variables: Variables) => Result
}
export const TypedDocumentNode = {}

export type DocumentTypeDecoration<Result, Variables> = TypedDocumentNode<Result, Variables>
export const DocumentTypeDecoration = {}

export type ResultOf<T> = T extends TypedDocumentNode<infer R, any> ? R : never
export const ResultOf = {}

export type VariablesOf<T> = T extends TypedDocumentNode<any, infer V> ? V : never
export const VariablesOf = {}
