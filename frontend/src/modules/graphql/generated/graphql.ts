/* eslint-disable */
import { TypedDocumentNode as DocumentNode } from '@graphql-typed-document-node/core';
export type Maybe<T> = T | null;
export type InputMaybe<T> = T | null | undefined;
export type Exact<T extends { [key: string]: unknown }> = { [K in keyof T]: T[K] };
export type MakeOptional<T, K extends keyof T> = Omit<T, K> & { [SubKey in K]?: Maybe<T[SubKey]> };
export type MakeMaybe<T, K extends keyof T> = Omit<T, K> & { [SubKey in K]: Maybe<T[SubKey]> };
export type MakeEmpty<T extends { [key: string]: unknown }, K extends keyof T> = { [_ in K]?: never };
export type Incremental<T> = T | { [P in keyof T]?: P extends ' $fragmentName' | '__typename' ? T[P] : never };
/** All built-in and custom scalars, mapped to their actual values */
export type Scalars = {
  ID: { input: string; output: string; }
  String: { input: string; output: string; }
  Boolean: { input: boolean; output: boolean; }
  Int: { input: number; output: number; }
  Float: { input: number; output: number; }
  /** Date with time (isoformat) */
  DateTime: { input: any; output: any; }
  /** The `JSON` scalar type represents JSON values as specified by [ECMA-404](https://ecma-international.org/wp-content/uploads/ECMA-404_2nd_edition_december_2017.pdf). */
  JSON: { input: any; output: any; }
};

export type Job = {
  __typename?: 'Job';
  completedAt?: Maybe<Scalars['DateTime']['output']>;
  createdAt: Scalars['DateTime']['output'];
  currentStep?: Maybe<Scalars['String']['output']>;
  error?: Maybe<Scalars['String']['output']>;
  jobId: Scalars['String']['output'];
  message: Scalars['String']['output'];
  progress: Scalars['Int']['output'];
  result?: Maybe<Scalars['JSON']['output']>;
  status: Scalars['String']['output'];
  total: Scalars['Int']['output'];
};

export type Mutation = {
  __typename?: 'Mutation';
  processRoute: Job;
  saveTrainingData: Scalars['String']['output'];
};


export type MutationProcessRouteArgs = {
  input: ProcessRouteInput;
};


export type MutationSaveTrainingDataArgs = {
  input: TrainingDataInput;
};

export type Point = {
  __typename?: 'Point';
  analysisMetadata?: Maybe<Scalars['JSON']['output']>;
  createdAt: Scalars['DateTime']['output'];
  damageCount: Scalars['Int']['output'];
  damageTypes?: Maybe<Scalars['JSON']['output']>;
  heading: Scalars['Float']['output'];
  id: Scalars['Int']['output'];
  imageUrl?: Maybe<Scalars['String']['output']>;
  latitude: Scalars['Float']['output'];
  localImagePath?: Maybe<Scalars['String']['output']>;
  longitude: Scalars['Float']['output'];
  manualAnnotations?: Maybe<Scalars['JSON']['output']>;
  manualComment?: Maybe<Scalars['String']['output']>;
  manualRqi?: Maybe<Scalars['Float']['output']>;
  manualTags?: Maybe<Array<Scalars['String']['output']>>;
  pitch?: Maybe<Scalars['Float']['output']>;
  rqiScore?: Maybe<Scalars['Float']['output']>;
};

export type ProcessRouteInput = {
  destinationLat: Scalars['Float']['input'];
  destinationLng: Scalars['Float']['input'];
  originLat: Scalars['Float']['input'];
  originLng: Scalars['Float']['input'];
};

export type Query = {
  __typename?: 'Query';
  config: Scalars['String']['output'];
  job?: Maybe<Job>;
  point?: Maybe<Point>;
  points: Array<Point>;
};


export type QueryJobArgs = {
  id: Scalars['String']['input'];
};


export type QueryPointArgs = {
  id: Scalars['Int']['input'];
};


export type QueryPointsArgs = {
  bbox?: InputMaybe<Array<Scalars['Float']['input']>>;
};

export type TrainingDataInput = {
  annotations?: InputMaybe<Scalars['JSON']['input']>;
  imageFilename: Scalars['String']['input'];
  manualComment?: InputMaybe<Scalars['String']['input']>;
  manualRqi?: InputMaybe<Scalars['Float']['input']>;
  metaData?: InputMaybe<Scalars['JSON']['input']>;
  tags?: InputMaybe<Array<Scalars['String']['input']>>;
};

export type GetPointsQueryVariables = Exact<{ [key: string]: never; }>;


export type GetPointsQuery = { __typename?: 'Query', points: Array<{ __typename?: 'Point', id: number, latitude: number, longitude: number, rqiScore?: number | null, heading: number }> };

export type GetPointDetailQueryVariables = Exact<{
  id: Scalars['Int']['input'];
}>;


export type GetPointDetailQuery = { __typename?: 'Query', point?: { __typename?: 'Point', id: number, latitude: number, longitude: number, rqiScore?: number | null, heading: number, pitch?: number | null, imageUrl?: string | null, manualRqi?: number | null, manualTags?: Array<string> | null, manualAnnotations?: any | null, damageCount: number, damageTypes?: any | null, analysisMetadata?: any | null, createdAt: any } | null };

export type GetTrainingDataQueryVariables = Exact<{
  id: Scalars['Int']['input'];
}>;


export type GetTrainingDataQuery = { __typename?: 'Query', point?: { __typename?: 'Point', imageUrl?: string | null, manualRqi?: number | null, manualTags?: Array<string> | null, manualAnnotations?: any | null, manualComment?: string | null } | null };

export type SaveTrainingDataMutationVariables = Exact<{
  input: TrainingDataInput;
}>;


export type SaveTrainingDataMutation = { __typename?: 'Mutation', saveTrainingData: string };


export const GetPointsDocument = {"kind":"Document","definitions":[{"kind":"OperationDefinition","operation":"query","name":{"kind":"Name","value":"GetPoints"},"selectionSet":{"kind":"SelectionSet","selections":[{"kind":"Field","name":{"kind":"Name","value":"points"},"selectionSet":{"kind":"SelectionSet","selections":[{"kind":"Field","name":{"kind":"Name","value":"id"}},{"kind":"Field","name":{"kind":"Name","value":"latitude"}},{"kind":"Field","name":{"kind":"Name","value":"longitude"}},{"kind":"Field","name":{"kind":"Name","value":"rqiScore"}},{"kind":"Field","name":{"kind":"Name","value":"heading"}}]}}]}}]} as unknown as DocumentNode<GetPointsQuery, GetPointsQueryVariables>;
export const GetPointDetailDocument = {"kind":"Document","definitions":[{"kind":"OperationDefinition","operation":"query","name":{"kind":"Name","value":"GetPointDetail"},"variableDefinitions":[{"kind":"VariableDefinition","variable":{"kind":"Variable","name":{"kind":"Name","value":"id"}},"type":{"kind":"NonNullType","type":{"kind":"NamedType","name":{"kind":"Name","value":"Int"}}}}],"selectionSet":{"kind":"SelectionSet","selections":[{"kind":"Field","name":{"kind":"Name","value":"point"},"arguments":[{"kind":"Argument","name":{"kind":"Name","value":"id"},"value":{"kind":"Variable","name":{"kind":"Name","value":"id"}}}],"selectionSet":{"kind":"SelectionSet","selections":[{"kind":"Field","name":{"kind":"Name","value":"id"}},{"kind":"Field","name":{"kind":"Name","value":"latitude"}},{"kind":"Field","name":{"kind":"Name","value":"longitude"}},{"kind":"Field","name":{"kind":"Name","value":"rqiScore"}},{"kind":"Field","name":{"kind":"Name","value":"heading"}},{"kind":"Field","name":{"kind":"Name","value":"pitch"}},{"kind":"Field","name":{"kind":"Name","value":"imageUrl"}},{"kind":"Field","name":{"kind":"Name","value":"manualRqi"}},{"kind":"Field","name":{"kind":"Name","value":"manualTags"}},{"kind":"Field","name":{"kind":"Name","value":"manualAnnotations"}},{"kind":"Field","name":{"kind":"Name","value":"damageCount"}},{"kind":"Field","name":{"kind":"Name","value":"damageTypes"}},{"kind":"Field","name":{"kind":"Name","value":"analysisMetadata"}},{"kind":"Field","name":{"kind":"Name","value":"createdAt"}}]}}]}}]} as unknown as DocumentNode<GetPointDetailQuery, GetPointDetailQueryVariables>;
export const GetTrainingDataDocument = {"kind":"Document","definitions":[{"kind":"OperationDefinition","operation":"query","name":{"kind":"Name","value":"GetTrainingData"},"variableDefinitions":[{"kind":"VariableDefinition","variable":{"kind":"Variable","name":{"kind":"Name","value":"id"}},"type":{"kind":"NonNullType","type":{"kind":"NamedType","name":{"kind":"Name","value":"Int"}}}}],"selectionSet":{"kind":"SelectionSet","selections":[{"kind":"Field","name":{"kind":"Name","value":"point"},"arguments":[{"kind":"Argument","name":{"kind":"Name","value":"id"},"value":{"kind":"Variable","name":{"kind":"Name","value":"id"}}}],"selectionSet":{"kind":"SelectionSet","selections":[{"kind":"Field","name":{"kind":"Name","value":"imageUrl"}},{"kind":"Field","name":{"kind":"Name","value":"manualRqi"}},{"kind":"Field","name":{"kind":"Name","value":"manualTags"}},{"kind":"Field","name":{"kind":"Name","value":"manualAnnotations"}},{"kind":"Field","name":{"kind":"Name","value":"manualComment"}}]}}]}}]} as unknown as DocumentNode<GetTrainingDataQuery, GetTrainingDataQueryVariables>;
export const SaveTrainingDataDocument = {"kind":"Document","definitions":[{"kind":"OperationDefinition","operation":"mutation","name":{"kind":"Name","value":"SaveTrainingData"},"variableDefinitions":[{"kind":"VariableDefinition","variable":{"kind":"Variable","name":{"kind":"Name","value":"input"}},"type":{"kind":"NonNullType","type":{"kind":"NamedType","name":{"kind":"Name","value":"TrainingDataInput"}}}}],"selectionSet":{"kind":"SelectionSet","selections":[{"kind":"Field","name":{"kind":"Name","value":"saveTrainingData"},"arguments":[{"kind":"Argument","name":{"kind":"Name","value":"input"},"value":{"kind":"Variable","name":{"kind":"Name","value":"input"}}}]}]}}]} as unknown as DocumentNode<SaveTrainingDataMutation, SaveTrainingDataMutationVariables>;