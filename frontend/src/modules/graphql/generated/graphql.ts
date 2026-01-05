/* eslint-disable */
import type { TypedDocumentNode as DocumentNode } from '@graphql-typed-document-node/core';
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

export type DetectInput = {
  classes?: InputMaybe<Array<Scalars['String']['input']>>;
  confThreshold?: InputMaybe<Scalars['Float']['input']>;
  filename: Scalars['String']['input'];
};

export type DetectPrediction = {
  __typename?: 'DetectPrediction';
  confidence: Scalars['Float']['output'];
  label: Scalars['String']['output'];
  points: Scalars['JSON']['output'];
};

export type FilterMode =
  | 'ALL'
  | 'PENDING'
  | 'REVIEWED';

export type Job = {
  __typename?: 'Job';
  completedAt?: Maybe<Scalars['DateTime']['output']>;
  createdAt: Scalars['DateTime']['output'];
  currentStep?: Maybe<Scalars['String']['output']>;
  details?: Maybe<Scalars['JSON']['output']>;
  error?: Maybe<Scalars['String']['output']>;
  id: Scalars['String']['output'];
  message: Scalars['String']['output'];
  progress: Scalars['Int']['output'];
  result?: Maybe<Scalars['JSON']['output']>;
  status: Scalars['String']['output'];
  total: Scalars['Int']['output'];
  type: Scalars['String']['output'];
};

export type Mutation = {
  __typename?: 'Mutation';
  applyPreset: Array<Setting>;
  deleteTrainingData: Scalars['Boolean']['output'];
  detectObjects: Array<DetectPrediction>;
  processRoute: Job;
  runAnalysis: Job;
  saveTrainingData: Scalars['String']['output'];
  startModelTraining: Job;
  stopJob: Scalars['Boolean']['output'];
  updateSetting: Setting;
};


export type MutationApplyPresetArgs = {
  values: Scalars['JSON']['input'];
};


export type MutationDeleteTrainingDataArgs = {
  imageFilename: Scalars['String']['input'];
};


export type MutationDetectObjectsArgs = {
  input: DetectInput;
};


export type MutationProcessRouteArgs = {
  input: ProcessRouteInput;
};


export type MutationRunAnalysisArgs = {
  input: RunAnalysisInput;
};


export type MutationSaveTrainingDataArgs = {
  input: TrainingDataInput;
};


export type MutationStopJobArgs = {
  jobId: Scalars['String']['input'];
};


export type MutationUpdateSettingArgs = {
  input: UpdateSettingInput;
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
  activeJob?: Maybe<Job>;
  availableModels: Array<Scalars['String']['output']>;
  config: Scalars['String']['output'];
  job?: Maybe<Job>;
  point?: Maybe<Point>;
  points: Array<Point>;
  settings: Array<Setting>;
  trainingPoints: TrainingPointsResponse;
  trainingStats: TrainingStats;
};


export type QueryJobArgs = {
  id: Scalars['String']['input'];
};


export type QueryPointArgs = {
  id: Scalars['Int']['input'];
};


export type QueryPointsArgs = {
  bbox?: InputMaybe<Array<Scalars['Float']['input']>>;
  limit?: Scalars['Int']['input'];
  offset?: Scalars['Int']['input'];
};


export type QueryTrainingPointsArgs = {
  limit?: Scalars['Int']['input'];
  mode?: FilterMode;
  offset?: Scalars['Int']['input'];
};


export type QueryTrainingStatsArgs = {
  mode?: FilterMode;
};

export type RunAnalysisInput = {
  limit?: Scalars['Int']['input'];
  reanalyze?: Scalars['Boolean']['input'];
  strategy: Scalars['String']['input'];
};

export type Setting = {
  __typename?: 'Setting';
  category?: Maybe<Scalars['String']['output']>;
  description?: Maybe<Scalars['String']['output']>;
  example?: Maybe<Scalars['String']['output']>;
  explanation?: Maybe<Scalars['String']['output']>;
  key: Scalars['String']['output'];
  value: Scalars['JSON']['output'];
};

export type TrainingDataInput = {
  annotations?: InputMaybe<Scalars['JSON']['input']>;
  imageFilename: Scalars['String']['input'];
  manualComment?: InputMaybe<Scalars['String']['input']>;
  manualRqi?: InputMaybe<Scalars['Float']['input']>;
  metaData?: InputMaybe<Scalars['JSON']['input']>;
  tags?: InputMaybe<Array<Scalars['String']['input']>>;
};

export type TrainingPointsResponse = {
  __typename?: 'TrainingPointsResponse';
  hasMore: Scalars['Boolean']['output'];
  items: Array<Point>;
  totalCount: Scalars['Int']['output'];
};

export type TrainingStats = {
  __typename?: 'TrainingStats';
  annotated: Scalars['Int']['output'];
  avgRqi: Scalars['Float']['output'];
  fairCount: Scalars['Int']['output'];
  goodCount: Scalars['Int']['output'];
  pending: Scalars['Int']['output'];
  pendingAnalysis: Scalars['Int']['output'];
  poorCount: Scalars['Int']['output'];
  total: Scalars['Int']['output'];
};

export type UpdateSettingInput = {
  key: Scalars['String']['input'];
  value: Scalars['JSON']['input'];
};

export type GetPointsQueryVariables = Exact<{
  limit?: InputMaybe<Scalars['Int']['input']>;
  bbox?: InputMaybe<Array<Scalars['Float']['input']> | Scalars['Float']['input']>;
}>;


export type GetPointsQuery = { __typename?: 'Query', points: Array<{ __typename?: 'Point', id: number, latitude: number, longitude: number, rqiScore?: number | null, heading: number }> };

export type GetPointDetailQueryVariables = Exact<{
  id: Scalars['Int']['input'];
}>;


export type GetPointDetailQuery = { __typename?: 'Query', point?: { __typename?: 'Point', id: number, latitude: number, longitude: number, rqiScore?: number | null, heading: number, pitch?: number | null, imageUrl?: string | null, manualRqi?: number | null, manualTags?: Array<string> | null, manualAnnotations?: any | null, damageCount: number, damageTypes?: any | null, analysisMetadata?: any | null, createdAt: any } | null };

export type GetAvailableModelsQueryVariables = Exact<{ [key: string]: never; }>;


export type GetAvailableModelsQuery = { __typename?: 'Query', availableModels: Array<string> };

export type GetSettingsQueryVariables = Exact<{ [key: string]: never; }>;


export type GetSettingsQuery = { __typename?: 'Query', settings: Array<{ __typename?: 'Setting', key: string, value: any, description?: string | null, example?: string | null, category?: string | null, explanation?: string | null }> };

export type UpdateSettingMutationVariables = Exact<{
  input: UpdateSettingInput;
}>;


export type UpdateSettingMutation = { __typename?: 'Mutation', updateSetting: { __typename?: 'Setting', key: string, value: any, description?: string | null, example?: string | null, category?: string | null, explanation?: string | null } };

export type ApplyPresetMutationVariables = Exact<{
  values: Scalars['JSON']['input'];
}>;


export type ApplyPresetMutation = { __typename?: 'Mutation', applyPreset: Array<{ __typename?: 'Setting', key: string, value: any, description?: string | null, example?: string | null, category?: string | null, explanation?: string | null }> };

export type GetTrainingDataQueryVariables = Exact<{
  id: Scalars['Int']['input'];
}>;


export type GetTrainingDataQuery = { __typename?: 'Query', point?: { __typename?: 'Point', imageUrl?: string | null, manualRqi?: number | null, manualTags?: Array<string> | null, manualAnnotations?: any | null, manualComment?: string | null } | null };

export type SaveTrainingDataMutationVariables = Exact<{
  input: TrainingDataInput;
}>;


export type SaveTrainingDataMutation = { __typename?: 'Mutation', saveTrainingData: string };

export type DeleteTrainingDataMutationVariables = Exact<{
  imageFilename: Scalars['String']['input'];
}>;


export type DeleteTrainingDataMutation = { __typename?: 'Mutation', deleteTrainingData: boolean };

export type GetTrainingPointsQueryVariables = Exact<{
  mode?: InputMaybe<FilterMode>;
  limit?: InputMaybe<Scalars['Int']['input']>;
  offset?: InputMaybe<Scalars['Int']['input']>;
}>;


export type GetTrainingPointsQuery = { __typename?: 'Query', trainingPoints: { __typename?: 'TrainingPointsResponse', totalCount: number, hasMore: boolean, items: Array<{ __typename?: 'Point', id: number, latitude: number, longitude: number, imageUrl?: string | null, rqiScore?: number | null, manualRqi?: number | null, manualTags?: Array<string> | null, createdAt: any }> } };

export type GetTrainingStatsQueryVariables = Exact<{
  mode?: InputMaybe<FilterMode>;
}>;


export type GetTrainingStatsQuery = { __typename?: 'Query', trainingStats: { __typename?: 'TrainingStats', total: number, pending: number, annotated: number, avgRqi: number, goodCount: number, fairCount: number, poorCount: number, pendingAnalysis: number } };

export type RunAnalysisMutationVariables = Exact<{
  input: RunAnalysisInput;
}>;


export type RunAnalysisMutation = { __typename?: 'Mutation', runAnalysis: { __typename?: 'Job', id: string } };

export type StartModelTrainingMutationVariables = Exact<{ [key: string]: never; }>;


export type StartModelTrainingMutation = { __typename?: 'Mutation', startModelTraining: { __typename?: 'Job', id: string } };

export type StopJobMutationVariables = Exact<{
  jobId: Scalars['String']['input'];
}>;


export type StopJobMutation = { __typename?: 'Mutation', stopJob: boolean };

export type GetActiveJobQueryVariables = Exact<{ [key: string]: never; }>;


export type GetActiveJobQuery = { __typename?: 'Query', activeJob?: { __typename?: 'Job', id: string, type: string, status: string, progress: number, total: number, details?: any | null, result?: any | null } | null };

export type GetJobQueryVariables = Exact<{
  id: Scalars['String']['input'];
}>;


export type GetJobQuery = { __typename?: 'Query', job?: { __typename?: 'Job', id: string, type: string, status: string, progress: number, total: number, details?: any | null, result?: any | null, createdAt: any, completedAt?: any | null } | null };

export type DetectObjectsMutationVariables = Exact<{
  input: DetectInput;
}>;


export type DetectObjectsMutation = { __typename?: 'Mutation', detectObjects: Array<{ __typename?: 'DetectPrediction', label: string, confidence: number, points: any }> };


export const GetPointsDocument = {"kind":"Document","definitions":[{"kind":"OperationDefinition","operation":"query","name":{"kind":"Name","value":"GetPoints"},"variableDefinitions":[{"kind":"VariableDefinition","variable":{"kind":"Variable","name":{"kind":"Name","value":"limit"}},"type":{"kind":"NamedType","name":{"kind":"Name","value":"Int"}}},{"kind":"VariableDefinition","variable":{"kind":"Variable","name":{"kind":"Name","value":"bbox"}},"type":{"kind":"ListType","type":{"kind":"NonNullType","type":{"kind":"NamedType","name":{"kind":"Name","value":"Float"}}}}}],"selectionSet":{"kind":"SelectionSet","selections":[{"kind":"Field","name":{"kind":"Name","value":"points"},"arguments":[{"kind":"Argument","name":{"kind":"Name","value":"limit"},"value":{"kind":"Variable","name":{"kind":"Name","value":"limit"}}},{"kind":"Argument","name":{"kind":"Name","value":"bbox"},"value":{"kind":"Variable","name":{"kind":"Name","value":"bbox"}}}],"selectionSet":{"kind":"SelectionSet","selections":[{"kind":"Field","name":{"kind":"Name","value":"id"}},{"kind":"Field","name":{"kind":"Name","value":"latitude"}},{"kind":"Field","name":{"kind":"Name","value":"longitude"}},{"kind":"Field","name":{"kind":"Name","value":"rqiScore"}},{"kind":"Field","name":{"kind":"Name","value":"heading"}}]}}]}}]} as unknown as DocumentNode<GetPointsQuery, GetPointsQueryVariables>;
export const GetPointDetailDocument = {"kind":"Document","definitions":[{"kind":"OperationDefinition","operation":"query","name":{"kind":"Name","value":"GetPointDetail"},"variableDefinitions":[{"kind":"VariableDefinition","variable":{"kind":"Variable","name":{"kind":"Name","value":"id"}},"type":{"kind":"NonNullType","type":{"kind":"NamedType","name":{"kind":"Name","value":"Int"}}}}],"selectionSet":{"kind":"SelectionSet","selections":[{"kind":"Field","name":{"kind":"Name","value":"point"},"arguments":[{"kind":"Argument","name":{"kind":"Name","value":"id"},"value":{"kind":"Variable","name":{"kind":"Name","value":"id"}}}],"selectionSet":{"kind":"SelectionSet","selections":[{"kind":"Field","name":{"kind":"Name","value":"id"}},{"kind":"Field","name":{"kind":"Name","value":"latitude"}},{"kind":"Field","name":{"kind":"Name","value":"longitude"}},{"kind":"Field","name":{"kind":"Name","value":"rqiScore"}},{"kind":"Field","name":{"kind":"Name","value":"heading"}},{"kind":"Field","name":{"kind":"Name","value":"pitch"}},{"kind":"Field","name":{"kind":"Name","value":"imageUrl"}},{"kind":"Field","name":{"kind":"Name","value":"manualRqi"}},{"kind":"Field","name":{"kind":"Name","value":"manualTags"}},{"kind":"Field","name":{"kind":"Name","value":"manualAnnotations"}},{"kind":"Field","name":{"kind":"Name","value":"damageCount"}},{"kind":"Field","name":{"kind":"Name","value":"damageTypes"}},{"kind":"Field","name":{"kind":"Name","value":"analysisMetadata"}},{"kind":"Field","name":{"kind":"Name","value":"createdAt"}}]}}]}}]} as unknown as DocumentNode<GetPointDetailQuery, GetPointDetailQueryVariables>;
export const GetAvailableModelsDocument = {"kind":"Document","definitions":[{"kind":"OperationDefinition","operation":"query","name":{"kind":"Name","value":"GetAvailableModels"},"selectionSet":{"kind":"SelectionSet","selections":[{"kind":"Field","name":{"kind":"Name","value":"availableModels"}}]}}]} as unknown as DocumentNode<GetAvailableModelsQuery, GetAvailableModelsQueryVariables>;
export const GetSettingsDocument = {"kind":"Document","definitions":[{"kind":"OperationDefinition","operation":"query","name":{"kind":"Name","value":"GetSettings"},"selectionSet":{"kind":"SelectionSet","selections":[{"kind":"Field","name":{"kind":"Name","value":"settings"},"selectionSet":{"kind":"SelectionSet","selections":[{"kind":"Field","name":{"kind":"Name","value":"key"}},{"kind":"Field","name":{"kind":"Name","value":"value"}},{"kind":"Field","name":{"kind":"Name","value":"description"}},{"kind":"Field","name":{"kind":"Name","value":"example"}},{"kind":"Field","name":{"kind":"Name","value":"category"}},{"kind":"Field","name":{"kind":"Name","value":"explanation"}}]}}]}}]} as unknown as DocumentNode<GetSettingsQuery, GetSettingsQueryVariables>;
export const UpdateSettingDocument = {"kind":"Document","definitions":[{"kind":"OperationDefinition","operation":"mutation","name":{"kind":"Name","value":"UpdateSetting"},"variableDefinitions":[{"kind":"VariableDefinition","variable":{"kind":"Variable","name":{"kind":"Name","value":"input"}},"type":{"kind":"NonNullType","type":{"kind":"NamedType","name":{"kind":"Name","value":"UpdateSettingInput"}}}}],"selectionSet":{"kind":"SelectionSet","selections":[{"kind":"Field","name":{"kind":"Name","value":"updateSetting"},"arguments":[{"kind":"Argument","name":{"kind":"Name","value":"input"},"value":{"kind":"Variable","name":{"kind":"Name","value":"input"}}}],"selectionSet":{"kind":"SelectionSet","selections":[{"kind":"Field","name":{"kind":"Name","value":"key"}},{"kind":"Field","name":{"kind":"Name","value":"value"}},{"kind":"Field","name":{"kind":"Name","value":"description"}},{"kind":"Field","name":{"kind":"Name","value":"example"}},{"kind":"Field","name":{"kind":"Name","value":"category"}},{"kind":"Field","name":{"kind":"Name","value":"explanation"}}]}}]}}]} as unknown as DocumentNode<UpdateSettingMutation, UpdateSettingMutationVariables>;
export const ApplyPresetDocument = {"kind":"Document","definitions":[{"kind":"OperationDefinition","operation":"mutation","name":{"kind":"Name","value":"ApplyPreset"},"variableDefinitions":[{"kind":"VariableDefinition","variable":{"kind":"Variable","name":{"kind":"Name","value":"values"}},"type":{"kind":"NonNullType","type":{"kind":"NamedType","name":{"kind":"Name","value":"JSON"}}}}],"selectionSet":{"kind":"SelectionSet","selections":[{"kind":"Field","name":{"kind":"Name","value":"applyPreset"},"arguments":[{"kind":"Argument","name":{"kind":"Name","value":"values"},"value":{"kind":"Variable","name":{"kind":"Name","value":"values"}}}],"selectionSet":{"kind":"SelectionSet","selections":[{"kind":"Field","name":{"kind":"Name","value":"key"}},{"kind":"Field","name":{"kind":"Name","value":"value"}},{"kind":"Field","name":{"kind":"Name","value":"description"}},{"kind":"Field","name":{"kind":"Name","value":"example"}},{"kind":"Field","name":{"kind":"Name","value":"category"}},{"kind":"Field","name":{"kind":"Name","value":"explanation"}}]}}]}}]} as unknown as DocumentNode<ApplyPresetMutation, ApplyPresetMutationVariables>;
export const GetTrainingDataDocument = {"kind":"Document","definitions":[{"kind":"OperationDefinition","operation":"query","name":{"kind":"Name","value":"GetTrainingData"},"variableDefinitions":[{"kind":"VariableDefinition","variable":{"kind":"Variable","name":{"kind":"Name","value":"id"}},"type":{"kind":"NonNullType","type":{"kind":"NamedType","name":{"kind":"Name","value":"Int"}}}}],"selectionSet":{"kind":"SelectionSet","selections":[{"kind":"Field","name":{"kind":"Name","value":"point"},"arguments":[{"kind":"Argument","name":{"kind":"Name","value":"id"},"value":{"kind":"Variable","name":{"kind":"Name","value":"id"}}}],"selectionSet":{"kind":"SelectionSet","selections":[{"kind":"Field","name":{"kind":"Name","value":"imageUrl"}},{"kind":"Field","name":{"kind":"Name","value":"manualRqi"}},{"kind":"Field","name":{"kind":"Name","value":"manualTags"}},{"kind":"Field","name":{"kind":"Name","value":"manualAnnotations"}},{"kind":"Field","name":{"kind":"Name","value":"manualComment"}}]}}]}}]} as unknown as DocumentNode<GetTrainingDataQuery, GetTrainingDataQueryVariables>;
export const SaveTrainingDataDocument = {"kind":"Document","definitions":[{"kind":"OperationDefinition","operation":"mutation","name":{"kind":"Name","value":"SaveTrainingData"},"variableDefinitions":[{"kind":"VariableDefinition","variable":{"kind":"Variable","name":{"kind":"Name","value":"input"}},"type":{"kind":"NonNullType","type":{"kind":"NamedType","name":{"kind":"Name","value":"TrainingDataInput"}}}}],"selectionSet":{"kind":"SelectionSet","selections":[{"kind":"Field","name":{"kind":"Name","value":"saveTrainingData"},"arguments":[{"kind":"Argument","name":{"kind":"Name","value":"input"},"value":{"kind":"Variable","name":{"kind":"Name","value":"input"}}}]}]}}]} as unknown as DocumentNode<SaveTrainingDataMutation, SaveTrainingDataMutationVariables>;
export const DeleteTrainingDataDocument = {"kind":"Document","definitions":[{"kind":"OperationDefinition","operation":"mutation","name":{"kind":"Name","value":"DeleteTrainingData"},"variableDefinitions":[{"kind":"VariableDefinition","variable":{"kind":"Variable","name":{"kind":"Name","value":"imageFilename"}},"type":{"kind":"NonNullType","type":{"kind":"NamedType","name":{"kind":"Name","value":"String"}}}}],"selectionSet":{"kind":"SelectionSet","selections":[{"kind":"Field","name":{"kind":"Name","value":"deleteTrainingData"},"arguments":[{"kind":"Argument","name":{"kind":"Name","value":"imageFilename"},"value":{"kind":"Variable","name":{"kind":"Name","value":"imageFilename"}}}]}]}}]} as unknown as DocumentNode<DeleteTrainingDataMutation, DeleteTrainingDataMutationVariables>;
export const GetTrainingPointsDocument = {"kind":"Document","definitions":[{"kind":"OperationDefinition","operation":"query","name":{"kind":"Name","value":"GetTrainingPoints"},"variableDefinitions":[{"kind":"VariableDefinition","variable":{"kind":"Variable","name":{"kind":"Name","value":"mode"}},"type":{"kind":"NamedType","name":{"kind":"Name","value":"FilterMode"}}},{"kind":"VariableDefinition","variable":{"kind":"Variable","name":{"kind":"Name","value":"limit"}},"type":{"kind":"NamedType","name":{"kind":"Name","value":"Int"}}},{"kind":"VariableDefinition","variable":{"kind":"Variable","name":{"kind":"Name","value":"offset"}},"type":{"kind":"NamedType","name":{"kind":"Name","value":"Int"}}}],"selectionSet":{"kind":"SelectionSet","selections":[{"kind":"Field","name":{"kind":"Name","value":"trainingPoints"},"arguments":[{"kind":"Argument","name":{"kind":"Name","value":"mode"},"value":{"kind":"Variable","name":{"kind":"Name","value":"mode"}}},{"kind":"Argument","name":{"kind":"Name","value":"limit"},"value":{"kind":"Variable","name":{"kind":"Name","value":"limit"}}},{"kind":"Argument","name":{"kind":"Name","value":"offset"},"value":{"kind":"Variable","name":{"kind":"Name","value":"offset"}}}],"selectionSet":{"kind":"SelectionSet","selections":[{"kind":"Field","name":{"kind":"Name","value":"items"},"selectionSet":{"kind":"SelectionSet","selections":[{"kind":"Field","name":{"kind":"Name","value":"id"}},{"kind":"Field","name":{"kind":"Name","value":"latitude"}},{"kind":"Field","name":{"kind":"Name","value":"longitude"}},{"kind":"Field","name":{"kind":"Name","value":"imageUrl"}},{"kind":"Field","name":{"kind":"Name","value":"rqiScore"}},{"kind":"Field","name":{"kind":"Name","value":"manualRqi"}},{"kind":"Field","name":{"kind":"Name","value":"manualTags"}},{"kind":"Field","name":{"kind":"Name","value":"createdAt"}}]}},{"kind":"Field","name":{"kind":"Name","value":"totalCount"}},{"kind":"Field","name":{"kind":"Name","value":"hasMore"}}]}}]}}]} as unknown as DocumentNode<GetTrainingPointsQuery, GetTrainingPointsQueryVariables>;
export const GetTrainingStatsDocument = {"kind":"Document","definitions":[{"kind":"OperationDefinition","operation":"query","name":{"kind":"Name","value":"GetTrainingStats"},"variableDefinitions":[{"kind":"VariableDefinition","variable":{"kind":"Variable","name":{"kind":"Name","value":"mode"}},"type":{"kind":"NamedType","name":{"kind":"Name","value":"FilterMode"}}}],"selectionSet":{"kind":"SelectionSet","selections":[{"kind":"Field","name":{"kind":"Name","value":"trainingStats"},"arguments":[{"kind":"Argument","name":{"kind":"Name","value":"mode"},"value":{"kind":"Variable","name":{"kind":"Name","value":"mode"}}}],"selectionSet":{"kind":"SelectionSet","selections":[{"kind":"Field","name":{"kind":"Name","value":"total"}},{"kind":"Field","name":{"kind":"Name","value":"pending"}},{"kind":"Field","name":{"kind":"Name","value":"annotated"}},{"kind":"Field","name":{"kind":"Name","value":"avgRqi"}},{"kind":"Field","name":{"kind":"Name","value":"goodCount"}},{"kind":"Field","name":{"kind":"Name","value":"fairCount"}},{"kind":"Field","name":{"kind":"Name","value":"poorCount"}},{"kind":"Field","name":{"kind":"Name","value":"pendingAnalysis"}}]}}]}}]} as unknown as DocumentNode<GetTrainingStatsQuery, GetTrainingStatsQueryVariables>;
export const RunAnalysisDocument = {"kind":"Document","definitions":[{"kind":"OperationDefinition","operation":"mutation","name":{"kind":"Name","value":"RunAnalysis"},"variableDefinitions":[{"kind":"VariableDefinition","variable":{"kind":"Variable","name":{"kind":"Name","value":"input"}},"type":{"kind":"NonNullType","type":{"kind":"NamedType","name":{"kind":"Name","value":"RunAnalysisInput"}}}}],"selectionSet":{"kind":"SelectionSet","selections":[{"kind":"Field","name":{"kind":"Name","value":"runAnalysis"},"arguments":[{"kind":"Argument","name":{"kind":"Name","value":"input"},"value":{"kind":"Variable","name":{"kind":"Name","value":"input"}}}],"selectionSet":{"kind":"SelectionSet","selections":[{"kind":"Field","name":{"kind":"Name","value":"id"}}]}}]}}]} as unknown as DocumentNode<RunAnalysisMutation, RunAnalysisMutationVariables>;
export const StartModelTrainingDocument = {"kind":"Document","definitions":[{"kind":"OperationDefinition","operation":"mutation","name":{"kind":"Name","value":"StartModelTraining"},"selectionSet":{"kind":"SelectionSet","selections":[{"kind":"Field","name":{"kind":"Name","value":"startModelTraining"},"selectionSet":{"kind":"SelectionSet","selections":[{"kind":"Field","name":{"kind":"Name","value":"id"}}]}}]}}]} as unknown as DocumentNode<StartModelTrainingMutation, StartModelTrainingMutationVariables>;
export const StopJobDocument = {"kind":"Document","definitions":[{"kind":"OperationDefinition","operation":"mutation","name":{"kind":"Name","value":"StopJob"},"variableDefinitions":[{"kind":"VariableDefinition","variable":{"kind":"Variable","name":{"kind":"Name","value":"jobId"}},"type":{"kind":"NonNullType","type":{"kind":"NamedType","name":{"kind":"Name","value":"String"}}}}],"selectionSet":{"kind":"SelectionSet","selections":[{"kind":"Field","name":{"kind":"Name","value":"stopJob"},"arguments":[{"kind":"Argument","name":{"kind":"Name","value":"jobId"},"value":{"kind":"Variable","name":{"kind":"Name","value":"jobId"}}}]}]}}]} as unknown as DocumentNode<StopJobMutation, StopJobMutationVariables>;
export const GetActiveJobDocument = {"kind":"Document","definitions":[{"kind":"OperationDefinition","operation":"query","name":{"kind":"Name","value":"GetActiveJob"},"selectionSet":{"kind":"SelectionSet","selections":[{"kind":"Field","name":{"kind":"Name","value":"activeJob"},"selectionSet":{"kind":"SelectionSet","selections":[{"kind":"Field","name":{"kind":"Name","value":"id"}},{"kind":"Field","name":{"kind":"Name","value":"type"}},{"kind":"Field","name":{"kind":"Name","value":"status"}},{"kind":"Field","name":{"kind":"Name","value":"progress"}},{"kind":"Field","name":{"kind":"Name","value":"total"}},{"kind":"Field","name":{"kind":"Name","value":"details"}},{"kind":"Field","name":{"kind":"Name","value":"result"}}]}}]}}]} as unknown as DocumentNode<GetActiveJobQuery, GetActiveJobQueryVariables>;
export const GetJobDocument = {"kind":"Document","definitions":[{"kind":"OperationDefinition","operation":"query","name":{"kind":"Name","value":"GetJob"},"variableDefinitions":[{"kind":"VariableDefinition","variable":{"kind":"Variable","name":{"kind":"Name","value":"id"}},"type":{"kind":"NonNullType","type":{"kind":"NamedType","name":{"kind":"Name","value":"String"}}}}],"selectionSet":{"kind":"SelectionSet","selections":[{"kind":"Field","name":{"kind":"Name","value":"job"},"arguments":[{"kind":"Argument","name":{"kind":"Name","value":"id"},"value":{"kind":"Variable","name":{"kind":"Name","value":"id"}}}],"selectionSet":{"kind":"SelectionSet","selections":[{"kind":"Field","name":{"kind":"Name","value":"id"}},{"kind":"Field","name":{"kind":"Name","value":"type"}},{"kind":"Field","name":{"kind":"Name","value":"status"}},{"kind":"Field","name":{"kind":"Name","value":"progress"}},{"kind":"Field","name":{"kind":"Name","value":"total"}},{"kind":"Field","name":{"kind":"Name","value":"details"}},{"kind":"Field","name":{"kind":"Name","value":"result"}},{"kind":"Field","name":{"kind":"Name","value":"createdAt"}},{"kind":"Field","name":{"kind":"Name","value":"completedAt"}}]}}]}}]} as unknown as DocumentNode<GetJobQuery, GetJobQueryVariables>;
export const DetectObjectsDocument = {"kind":"Document","definitions":[{"kind":"OperationDefinition","operation":"mutation","name":{"kind":"Name","value":"DetectObjects"},"variableDefinitions":[{"kind":"VariableDefinition","variable":{"kind":"Variable","name":{"kind":"Name","value":"input"}},"type":{"kind":"NonNullType","type":{"kind":"NamedType","name":{"kind":"Name","value":"DetectInput"}}}}],"selectionSet":{"kind":"SelectionSet","selections":[{"kind":"Field","name":{"kind":"Name","value":"detectObjects"},"arguments":[{"kind":"Argument","name":{"kind":"Name","value":"input"},"value":{"kind":"Variable","name":{"kind":"Name","value":"input"}}}],"selectionSet":{"kind":"SelectionSet","selections":[{"kind":"Field","name":{"kind":"Name","value":"label"}},{"kind":"Field","name":{"kind":"Name","value":"confidence"}},{"kind":"Field","name":{"kind":"Name","value":"points"}}]}}]}}]} as unknown as DocumentNode<DetectObjectsMutation, DetectObjectsMutationVariables>;