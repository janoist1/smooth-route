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

export type Annotation = {
  __typename?: 'Annotation';
  id: Scalars['String']['output'];
  label: Scalars['String']['output'];
  points: Scalars['JSON']['output'];
  score: Scalars['Float']['output'];
  type: Scalars['String']['output'];
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
  performReviewAction: ReviewActionResult;
  predictDinoRqi?: Maybe<Scalars['Int']['output']>;
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


export type MutationPerformReviewActionArgs = {
  input: ReviewActionInput;
};


export type MutationPredictDinoRqiArgs = {
  imageFilename: Scalars['String']['input'];
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
  dinoPBad?: Maybe<Scalars['Float']['output']>;
  dinoRqiScore?: Maybe<Scalars['Float']['output']>;
  dinoScore?: Maybe<Scalars['Float']['output']>;
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
  rqiSource: Scalars['String']['output'];
};

export type ProcessRouteInput = {
  destination: Scalars['String']['input'];
  origin: Scalars['String']['input'];
};

export type Query = {
  __typename?: 'Query';
  activeJob?: Maybe<Job>;
  availableModels: Array<Scalars['String']['output']>;
  config: Scalars['String']['output'];
  getRoute?: Maybe<RouteData>;
  job?: Maybe<Job>;
  nextTrainingPoint?: Maybe<Scalars['Int']['output']>;
  point?: Maybe<Point>;
  points: Array<Point>;
  rqiModelInfo: RqiModelInfo;
  settings: Array<Setting>;
  trainingPoints: TrainingPointsResponse;
  trainingStats: TrainingStats;
};


export type QueryGetRouteArgs = {
  destination: Scalars['String']['input'];
  origin: Scalars['String']['input'];
};


export type QueryJobArgs = {
  id: Scalars['String']['input'];
};


export type QueryNextTrainingPointArgs = {
  currentId: Scalars['Int']['input'];
  mode?: FilterMode;
  model?: Scalars['String']['input'];
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
  model?: Scalars['String']['input'];
  offset?: Scalars['Int']['input'];
};


export type QueryTrainingStatsArgs = {
  isDino?: Scalars['Boolean']['input'];
  mode?: FilterMode;
};

export type ReviewActionInput = {
  actionType: Scalars['String']['input'];
  parameters: Scalars['JSON']['input'];
};

export type ReviewActionResult = {
  __typename?: 'ReviewActionResult';
  annotations?: Maybe<Array<Annotation>>;
  message?: Maybe<Scalars['String']['output']>;
  processedImageUrl?: Maybe<Scalars['String']['output']>;
  success: Scalars['Boolean']['output'];
};

export type RouteData = {
  __typename?: 'RouteData';
  points: Array<RouteStep>;
};

export type RouteStep = {
  __typename?: 'RouteStep';
  lat: Scalars['Float']['output'];
  lng: Scalars['Float']['output'];
};

export type RqiModelInfo = {
  __typename?: 'RqiModelInfo';
  available: Scalars['Boolean']['output'];
  backbone?: Maybe<Scalars['String']['output']>;
  badRoadAcc?: Maybe<Scalars['Float']['output']>;
  badRoadAuc?: Maybe<Scalars['Float']['output']>;
  exactAcc?: Maybe<Scalars['Float']['output']>;
  head?: Maybe<Scalars['String']['output']>;
  mae?: Maybe<Scalars['Float']['output']>;
  nTrain?: Maybe<Scalars['Int']['output']>;
  qwk?: Maybe<Scalars['Float']['output']>;
  recipe?: Maybe<Scalars['String']['output']>;
  scaleMeaning?: Maybe<Scalars['String']['output']>;
  version?: Maybe<Scalars['Int']['output']>;
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
  rqi1Count: Scalars['Int']['output'];
  rqi2Count: Scalars['Int']['output'];
  rqi3Count: Scalars['Int']['output'];
  rqi4Count: Scalars['Int']['output'];
  rqi5Count: Scalars['Int']['output'];
  total: Scalars['Int']['output'];
};

export type UpdateSettingInput = {
  key: Scalars['String']['input'];
  value: Scalars['JSON']['input'];
};

export type GetJobQueryVariables = Exact<{
  id: Scalars['String']['input'];
}>;


export type GetJobQuery = { __typename?: 'Query', job?: { __typename?: 'Job', id: string, status: string, progress: number, total: number, message: string, result?: any | null, error?: string | null, createdAt: any, completedAt?: any | null } | null };

export type GetPointsQueryVariables = Exact<{
  limit?: InputMaybe<Scalars['Int']['input']>;
  bbox?: InputMaybe<Array<Scalars['Float']['input']> | Scalars['Float']['input']>;
}>;


export type GetPointsQuery = { __typename?: 'Query', points: Array<{ __typename?: 'Point', id: number, latitude: number, longitude: number, rqiScore?: number | null, dinoRqiScore?: number | null, rqiSource: string, heading: number }> };

export type GetPointDetailQueryVariables = Exact<{
  id: Scalars['Int']['input'];
}>;


export type GetPointDetailQuery = { __typename?: 'Query', point?: { __typename?: 'Point', id: number, latitude: number, longitude: number, rqiScore?: number | null, dinoRqiScore?: number | null, dinoScore?: number | null, dinoPBad?: number | null, rqiSource: string, heading: number, pitch?: number | null, imageUrl?: string | null, manualRqi?: number | null, manualTags?: Array<string> | null, manualAnnotations?: any | null, damageCount: number, damageTypes?: any | null, analysisMetadata?: any | null, createdAt: any } | null };

export type GetRouteQueryVariables = Exact<{
  origin: Scalars['String']['input'];
  destination: Scalars['String']['input'];
}>;


export type GetRouteQuery = { __typename?: 'Query', getRoute?: { __typename?: 'RouteData', points: Array<{ __typename?: 'RouteStep', lat: number, lng: number }> } | null };

export type ProcessRouteMutationVariables = Exact<{
  input: ProcessRouteInput;
}>;


export type ProcessRouteMutation = { __typename?: 'Mutation', processRoute: { __typename?: 'Job', id: string, status: string, message: string } };

export type GetActiveJobQueryVariables = Exact<{ [key: string]: never; }>;


export type GetActiveJobQuery = { __typename?: 'Query', activeJob?: { __typename?: 'Job', id: string, type: string, status: string, progress: number, total: number, details?: any | null, result?: any | null } | null };

export type GetAvailableModelsQueryVariables = Exact<{ [key: string]: never; }>;


export type GetAvailableModelsQuery = { __typename?: 'Query', availableModels: Array<string> };

export type GetSettingsQueryVariables = Exact<{ [key: string]: never; }>;


export type GetSettingsQuery = { __typename?: 'Query', settings: Array<{ __typename?: 'Setting', key: string, value: any, description?: string | null, example?: string | null, category?: string | null, explanation?: string | null }> };

export type UpdateSettingMutationVariables = Exact<{
  input: UpdateSettingInput;
}>;


export type UpdateSettingMutation = { __typename?: 'Mutation', updateSetting: { __typename?: 'Setting', key: string, value: any, description?: string | null, example?: string | null, category?: string | null, explanation?: string | null } };

export type GetRqiModelInfoQueryVariables = Exact<{ [key: string]: never; }>;


export type GetRqiModelInfoQuery = { __typename?: 'Query', rqiModelInfo: { __typename?: 'RqiModelInfo', available: boolean, version?: number | null, backbone?: string | null, recipe?: string | null, head?: string | null, nTrain?: number | null, qwk?: number | null, mae?: number | null, exactAcc?: number | null, badRoadAcc?: number | null, badRoadAuc?: number | null, scaleMeaning?: string | null } };

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
  model?: InputMaybe<Scalars['String']['input']>;
}>;


export type GetTrainingPointsQuery = { __typename?: 'Query', trainingPoints: { __typename?: 'TrainingPointsResponse', totalCount: number, hasMore: boolean, items: Array<{ __typename?: 'Point', id: number, latitude: number, longitude: number, imageUrl?: string | null, rqiScore?: number | null, dinoRqiScore?: number | null, manualRqi?: number | null }> } };

export type GetTrainingStatsQueryVariables = Exact<{
  mode?: InputMaybe<FilterMode>;
  isDino?: InputMaybe<Scalars['Boolean']['input']>;
}>;


export type GetTrainingStatsQuery = { __typename?: 'Query', trainingStats: { __typename?: 'TrainingStats', total: number, pending: number, annotated: number, avgRqi: number, goodCount: number, fairCount: number, poorCount: number, pendingAnalysis: number, rqi1Count: number, rqi2Count: number, rqi3Count: number, rqi4Count: number, rqi5Count: number } };

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

export type PerformReviewActionMutationVariables = Exact<{
  input: ReviewActionInput;
}>;


export type PerformReviewActionMutation = { __typename?: 'Mutation', performReviewAction: { __typename?: 'ReviewActionResult', success: boolean, message?: string | null, processedImageUrl?: string | null, annotations?: Array<{ __typename?: 'Annotation', id: string, label: string, score: number, type: string, points: any }> | null } };


export const GetJobDocument = {"kind":"Document","definitions":[{"kind":"OperationDefinition","operation":"query","name":{"kind":"Name","value":"GetJob"},"variableDefinitions":[{"kind":"VariableDefinition","variable":{"kind":"Variable","name":{"kind":"Name","value":"id"}},"type":{"kind":"NonNullType","type":{"kind":"NamedType","name":{"kind":"Name","value":"String"}}}}],"selectionSet":{"kind":"SelectionSet","selections":[{"kind":"Field","name":{"kind":"Name","value":"job"},"arguments":[{"kind":"Argument","name":{"kind":"Name","value":"id"},"value":{"kind":"Variable","name":{"kind":"Name","value":"id"}}}],"selectionSet":{"kind":"SelectionSet","selections":[{"kind":"Field","name":{"kind":"Name","value":"id"}},{"kind":"Field","name":{"kind":"Name","value":"status"}},{"kind":"Field","name":{"kind":"Name","value":"progress"}},{"kind":"Field","name":{"kind":"Name","value":"total"}},{"kind":"Field","name":{"kind":"Name","value":"message"}},{"kind":"Field","name":{"kind":"Name","value":"result"}},{"kind":"Field","name":{"kind":"Name","value":"error"}},{"kind":"Field","name":{"kind":"Name","value":"createdAt"}},{"kind":"Field","name":{"kind":"Name","value":"completedAt"}}]}}]}}]} as unknown as DocumentNode<GetJobQuery, GetJobQueryVariables>;
export const GetPointsDocument = {"kind":"Document","definitions":[{"kind":"OperationDefinition","operation":"query","name":{"kind":"Name","value":"GetPoints"},"variableDefinitions":[{"kind":"VariableDefinition","variable":{"kind":"Variable","name":{"kind":"Name","value":"limit"}},"type":{"kind":"NamedType","name":{"kind":"Name","value":"Int"}}},{"kind":"VariableDefinition","variable":{"kind":"Variable","name":{"kind":"Name","value":"bbox"}},"type":{"kind":"ListType","type":{"kind":"NonNullType","type":{"kind":"NamedType","name":{"kind":"Name","value":"Float"}}}}}],"selectionSet":{"kind":"SelectionSet","selections":[{"kind":"Field","name":{"kind":"Name","value":"points"},"arguments":[{"kind":"Argument","name":{"kind":"Name","value":"limit"},"value":{"kind":"Variable","name":{"kind":"Name","value":"limit"}}},{"kind":"Argument","name":{"kind":"Name","value":"bbox"},"value":{"kind":"Variable","name":{"kind":"Name","value":"bbox"}}}],"selectionSet":{"kind":"SelectionSet","selections":[{"kind":"Field","name":{"kind":"Name","value":"id"}},{"kind":"Field","name":{"kind":"Name","value":"latitude"}},{"kind":"Field","name":{"kind":"Name","value":"longitude"}},{"kind":"Field","name":{"kind":"Name","value":"rqiScore"}},{"kind":"Field","name":{"kind":"Name","value":"dinoRqiScore"}},{"kind":"Field","name":{"kind":"Name","value":"rqiSource"}},{"kind":"Field","name":{"kind":"Name","value":"heading"}}]}}]}}]} as unknown as DocumentNode<GetPointsQuery, GetPointsQueryVariables>;
export const GetPointDetailDocument = {"kind":"Document","definitions":[{"kind":"OperationDefinition","operation":"query","name":{"kind":"Name","value":"GetPointDetail"},"variableDefinitions":[{"kind":"VariableDefinition","variable":{"kind":"Variable","name":{"kind":"Name","value":"id"}},"type":{"kind":"NonNullType","type":{"kind":"NamedType","name":{"kind":"Name","value":"Int"}}}}],"selectionSet":{"kind":"SelectionSet","selections":[{"kind":"Field","name":{"kind":"Name","value":"point"},"arguments":[{"kind":"Argument","name":{"kind":"Name","value":"id"},"value":{"kind":"Variable","name":{"kind":"Name","value":"id"}}}],"selectionSet":{"kind":"SelectionSet","selections":[{"kind":"Field","name":{"kind":"Name","value":"id"}},{"kind":"Field","name":{"kind":"Name","value":"latitude"}},{"kind":"Field","name":{"kind":"Name","value":"longitude"}},{"kind":"Field","name":{"kind":"Name","value":"rqiScore"}},{"kind":"Field","name":{"kind":"Name","value":"dinoRqiScore"}},{"kind":"Field","name":{"kind":"Name","value":"dinoScore"}},{"kind":"Field","name":{"kind":"Name","value":"dinoPBad"}},{"kind":"Field","name":{"kind":"Name","value":"rqiSource"}},{"kind":"Field","name":{"kind":"Name","value":"heading"}},{"kind":"Field","name":{"kind":"Name","value":"pitch"}},{"kind":"Field","name":{"kind":"Name","value":"imageUrl"}},{"kind":"Field","name":{"kind":"Name","value":"manualRqi"}},{"kind":"Field","name":{"kind":"Name","value":"manualTags"}},{"kind":"Field","name":{"kind":"Name","value":"manualAnnotations"}},{"kind":"Field","name":{"kind":"Name","value":"damageCount"}},{"kind":"Field","name":{"kind":"Name","value":"damageTypes"}},{"kind":"Field","name":{"kind":"Name","value":"analysisMetadata"}},{"kind":"Field","name":{"kind":"Name","value":"createdAt"}}]}}]}}]} as unknown as DocumentNode<GetPointDetailQuery, GetPointDetailQueryVariables>;
export const GetRouteDocument = {"kind":"Document","definitions":[{"kind":"OperationDefinition","operation":"query","name":{"kind":"Name","value":"GetRoute"},"variableDefinitions":[{"kind":"VariableDefinition","variable":{"kind":"Variable","name":{"kind":"Name","value":"origin"}},"type":{"kind":"NonNullType","type":{"kind":"NamedType","name":{"kind":"Name","value":"String"}}}},{"kind":"VariableDefinition","variable":{"kind":"Variable","name":{"kind":"Name","value":"destination"}},"type":{"kind":"NonNullType","type":{"kind":"NamedType","name":{"kind":"Name","value":"String"}}}}],"selectionSet":{"kind":"SelectionSet","selections":[{"kind":"Field","name":{"kind":"Name","value":"getRoute"},"arguments":[{"kind":"Argument","name":{"kind":"Name","value":"origin"},"value":{"kind":"Variable","name":{"kind":"Name","value":"origin"}}},{"kind":"Argument","name":{"kind":"Name","value":"destination"},"value":{"kind":"Variable","name":{"kind":"Name","value":"destination"}}}],"selectionSet":{"kind":"SelectionSet","selections":[{"kind":"Field","name":{"kind":"Name","value":"points"},"selectionSet":{"kind":"SelectionSet","selections":[{"kind":"Field","name":{"kind":"Name","value":"lat"}},{"kind":"Field","name":{"kind":"Name","value":"lng"}}]}}]}}]}}]} as unknown as DocumentNode<GetRouteQuery, GetRouteQueryVariables>;
export const ProcessRouteDocument = {"kind":"Document","definitions":[{"kind":"OperationDefinition","operation":"mutation","name":{"kind":"Name","value":"ProcessRoute"},"variableDefinitions":[{"kind":"VariableDefinition","variable":{"kind":"Variable","name":{"kind":"Name","value":"input"}},"type":{"kind":"NonNullType","type":{"kind":"NamedType","name":{"kind":"Name","value":"ProcessRouteInput"}}}}],"selectionSet":{"kind":"SelectionSet","selections":[{"kind":"Field","name":{"kind":"Name","value":"processRoute"},"arguments":[{"kind":"Argument","name":{"kind":"Name","value":"input"},"value":{"kind":"Variable","name":{"kind":"Name","value":"input"}}}],"selectionSet":{"kind":"SelectionSet","selections":[{"kind":"Field","name":{"kind":"Name","value":"id"}},{"kind":"Field","name":{"kind":"Name","value":"status"}},{"kind":"Field","name":{"kind":"Name","value":"message"}}]}}]}}]} as unknown as DocumentNode<ProcessRouteMutation, ProcessRouteMutationVariables>;
export const GetActiveJobDocument = {"kind":"Document","definitions":[{"kind":"OperationDefinition","operation":"query","name":{"kind":"Name","value":"GetActiveJob"},"selectionSet":{"kind":"SelectionSet","selections":[{"kind":"Field","name":{"kind":"Name","value":"activeJob"},"selectionSet":{"kind":"SelectionSet","selections":[{"kind":"Field","name":{"kind":"Name","value":"id"}},{"kind":"Field","name":{"kind":"Name","value":"type"}},{"kind":"Field","name":{"kind":"Name","value":"status"}},{"kind":"Field","name":{"kind":"Name","value":"progress"}},{"kind":"Field","name":{"kind":"Name","value":"total"}},{"kind":"Field","name":{"kind":"Name","value":"details"}},{"kind":"Field","name":{"kind":"Name","value":"result"}}]}}]}}]} as unknown as DocumentNode<GetActiveJobQuery, GetActiveJobQueryVariables>;
export const GetAvailableModelsDocument = {"kind":"Document","definitions":[{"kind":"OperationDefinition","operation":"query","name":{"kind":"Name","value":"GetAvailableModels"},"selectionSet":{"kind":"SelectionSet","selections":[{"kind":"Field","name":{"kind":"Name","value":"availableModels"}}]}}]} as unknown as DocumentNode<GetAvailableModelsQuery, GetAvailableModelsQueryVariables>;
export const GetSettingsDocument = {"kind":"Document","definitions":[{"kind":"OperationDefinition","operation":"query","name":{"kind":"Name","value":"GetSettings"},"selectionSet":{"kind":"SelectionSet","selections":[{"kind":"Field","name":{"kind":"Name","value":"settings"},"selectionSet":{"kind":"SelectionSet","selections":[{"kind":"Field","name":{"kind":"Name","value":"key"}},{"kind":"Field","name":{"kind":"Name","value":"value"}},{"kind":"Field","name":{"kind":"Name","value":"description"}},{"kind":"Field","name":{"kind":"Name","value":"example"}},{"kind":"Field","name":{"kind":"Name","value":"category"}},{"kind":"Field","name":{"kind":"Name","value":"explanation"}}]}}]}}]} as unknown as DocumentNode<GetSettingsQuery, GetSettingsQueryVariables>;
export const UpdateSettingDocument = {"kind":"Document","definitions":[{"kind":"OperationDefinition","operation":"mutation","name":{"kind":"Name","value":"UpdateSetting"},"variableDefinitions":[{"kind":"VariableDefinition","variable":{"kind":"Variable","name":{"kind":"Name","value":"input"}},"type":{"kind":"NonNullType","type":{"kind":"NamedType","name":{"kind":"Name","value":"UpdateSettingInput"}}}}],"selectionSet":{"kind":"SelectionSet","selections":[{"kind":"Field","name":{"kind":"Name","value":"updateSetting"},"arguments":[{"kind":"Argument","name":{"kind":"Name","value":"input"},"value":{"kind":"Variable","name":{"kind":"Name","value":"input"}}}],"selectionSet":{"kind":"SelectionSet","selections":[{"kind":"Field","name":{"kind":"Name","value":"key"}},{"kind":"Field","name":{"kind":"Name","value":"value"}},{"kind":"Field","name":{"kind":"Name","value":"description"}},{"kind":"Field","name":{"kind":"Name","value":"example"}},{"kind":"Field","name":{"kind":"Name","value":"category"}},{"kind":"Field","name":{"kind":"Name","value":"explanation"}}]}}]}}]} as unknown as DocumentNode<UpdateSettingMutation, UpdateSettingMutationVariables>;
export const GetRqiModelInfoDocument = {"kind":"Document","definitions":[{"kind":"OperationDefinition","operation":"query","name":{"kind":"Name","value":"GetRqiModelInfo"},"selectionSet":{"kind":"SelectionSet","selections":[{"kind":"Field","name":{"kind":"Name","value":"rqiModelInfo"},"selectionSet":{"kind":"SelectionSet","selections":[{"kind":"Field","name":{"kind":"Name","value":"available"}},{"kind":"Field","name":{"kind":"Name","value":"version"}},{"kind":"Field","name":{"kind":"Name","value":"backbone"}},{"kind":"Field","name":{"kind":"Name","value":"recipe"}},{"kind":"Field","name":{"kind":"Name","value":"head"}},{"kind":"Field","name":{"kind":"Name","value":"nTrain"}},{"kind":"Field","name":{"kind":"Name","value":"qwk"}},{"kind":"Field","name":{"kind":"Name","value":"mae"}},{"kind":"Field","name":{"kind":"Name","value":"exactAcc"}},{"kind":"Field","name":{"kind":"Name","value":"badRoadAcc"}},{"kind":"Field","name":{"kind":"Name","value":"badRoadAuc"}},{"kind":"Field","name":{"kind":"Name","value":"scaleMeaning"}}]}}]}}]} as unknown as DocumentNode<GetRqiModelInfoQuery, GetRqiModelInfoQueryVariables>;
export const GetTrainingDataDocument = {"kind":"Document","definitions":[{"kind":"OperationDefinition","operation":"query","name":{"kind":"Name","value":"GetTrainingData"},"variableDefinitions":[{"kind":"VariableDefinition","variable":{"kind":"Variable","name":{"kind":"Name","value":"id"}},"type":{"kind":"NonNullType","type":{"kind":"NamedType","name":{"kind":"Name","value":"Int"}}}}],"selectionSet":{"kind":"SelectionSet","selections":[{"kind":"Field","name":{"kind":"Name","value":"point"},"arguments":[{"kind":"Argument","name":{"kind":"Name","value":"id"},"value":{"kind":"Variable","name":{"kind":"Name","value":"id"}}}],"selectionSet":{"kind":"SelectionSet","selections":[{"kind":"Field","name":{"kind":"Name","value":"imageUrl"}},{"kind":"Field","name":{"kind":"Name","value":"manualRqi"}},{"kind":"Field","name":{"kind":"Name","value":"manualTags"}},{"kind":"Field","name":{"kind":"Name","value":"manualAnnotations"}},{"kind":"Field","name":{"kind":"Name","value":"manualComment"}}]}}]}}]} as unknown as DocumentNode<GetTrainingDataQuery, GetTrainingDataQueryVariables>;
export const SaveTrainingDataDocument = {"kind":"Document","definitions":[{"kind":"OperationDefinition","operation":"mutation","name":{"kind":"Name","value":"SaveTrainingData"},"variableDefinitions":[{"kind":"VariableDefinition","variable":{"kind":"Variable","name":{"kind":"Name","value":"input"}},"type":{"kind":"NonNullType","type":{"kind":"NamedType","name":{"kind":"Name","value":"TrainingDataInput"}}}}],"selectionSet":{"kind":"SelectionSet","selections":[{"kind":"Field","name":{"kind":"Name","value":"saveTrainingData"},"arguments":[{"kind":"Argument","name":{"kind":"Name","value":"input"},"value":{"kind":"Variable","name":{"kind":"Name","value":"input"}}}]}]}}]} as unknown as DocumentNode<SaveTrainingDataMutation, SaveTrainingDataMutationVariables>;
export const DeleteTrainingDataDocument = {"kind":"Document","definitions":[{"kind":"OperationDefinition","operation":"mutation","name":{"kind":"Name","value":"DeleteTrainingData"},"variableDefinitions":[{"kind":"VariableDefinition","variable":{"kind":"Variable","name":{"kind":"Name","value":"imageFilename"}},"type":{"kind":"NonNullType","type":{"kind":"NamedType","name":{"kind":"Name","value":"String"}}}}],"selectionSet":{"kind":"SelectionSet","selections":[{"kind":"Field","name":{"kind":"Name","value":"deleteTrainingData"},"arguments":[{"kind":"Argument","name":{"kind":"Name","value":"imageFilename"},"value":{"kind":"Variable","name":{"kind":"Name","value":"imageFilename"}}}]}]}}]} as unknown as DocumentNode<DeleteTrainingDataMutation, DeleteTrainingDataMutationVariables>;
export const GetTrainingPointsDocument = {"kind":"Document","definitions":[{"kind":"OperationDefinition","operation":"query","name":{"kind":"Name","value":"GetTrainingPoints"},"variableDefinitions":[{"kind":"VariableDefinition","variable":{"kind":"Variable","name":{"kind":"Name","value":"mode"}},"type":{"kind":"NamedType","name":{"kind":"Name","value":"FilterMode"}}},{"kind":"VariableDefinition","variable":{"kind":"Variable","name":{"kind":"Name","value":"limit"}},"type":{"kind":"NamedType","name":{"kind":"Name","value":"Int"}}},{"kind":"VariableDefinition","variable":{"kind":"Variable","name":{"kind":"Name","value":"offset"}},"type":{"kind":"NamedType","name":{"kind":"Name","value":"Int"}}},{"kind":"VariableDefinition","variable":{"kind":"Variable","name":{"kind":"Name","value":"model"}},"type":{"kind":"NamedType","name":{"kind":"Name","value":"String"}}}],"selectionSet":{"kind":"SelectionSet","selections":[{"kind":"Field","name":{"kind":"Name","value":"trainingPoints"},"arguments":[{"kind":"Argument","name":{"kind":"Name","value":"mode"},"value":{"kind":"Variable","name":{"kind":"Name","value":"mode"}}},{"kind":"Argument","name":{"kind":"Name","value":"limit"},"value":{"kind":"Variable","name":{"kind":"Name","value":"limit"}}},{"kind":"Argument","name":{"kind":"Name","value":"offset"},"value":{"kind":"Variable","name":{"kind":"Name","value":"offset"}}},{"kind":"Argument","name":{"kind":"Name","value":"model"},"value":{"kind":"Variable","name":{"kind":"Name","value":"model"}}}],"selectionSet":{"kind":"SelectionSet","selections":[{"kind":"Field","name":{"kind":"Name","value":"items"},"selectionSet":{"kind":"SelectionSet","selections":[{"kind":"Field","name":{"kind":"Name","value":"id"}},{"kind":"Field","name":{"kind":"Name","value":"latitude"}},{"kind":"Field","name":{"kind":"Name","value":"longitude"}},{"kind":"Field","name":{"kind":"Name","value":"imageUrl"}},{"kind":"Field","name":{"kind":"Name","value":"rqiScore"}},{"kind":"Field","name":{"kind":"Name","value":"dinoRqiScore"}},{"kind":"Field","name":{"kind":"Name","value":"manualRqi"}}]}},{"kind":"Field","name":{"kind":"Name","value":"totalCount"}},{"kind":"Field","name":{"kind":"Name","value":"hasMore"}}]}}]}}]} as unknown as DocumentNode<GetTrainingPointsQuery, GetTrainingPointsQueryVariables>;
export const GetTrainingStatsDocument = {"kind":"Document","definitions":[{"kind":"OperationDefinition","operation":"query","name":{"kind":"Name","value":"GetTrainingStats"},"variableDefinitions":[{"kind":"VariableDefinition","variable":{"kind":"Variable","name":{"kind":"Name","value":"mode"}},"type":{"kind":"NamedType","name":{"kind":"Name","value":"FilterMode"}}},{"kind":"VariableDefinition","variable":{"kind":"Variable","name":{"kind":"Name","value":"isDino"}},"type":{"kind":"NamedType","name":{"kind":"Name","value":"Boolean"}}}],"selectionSet":{"kind":"SelectionSet","selections":[{"kind":"Field","name":{"kind":"Name","value":"trainingStats"},"arguments":[{"kind":"Argument","name":{"kind":"Name","value":"mode"},"value":{"kind":"Variable","name":{"kind":"Name","value":"mode"}}},{"kind":"Argument","name":{"kind":"Name","value":"isDino"},"value":{"kind":"Variable","name":{"kind":"Name","value":"isDino"}}}],"selectionSet":{"kind":"SelectionSet","selections":[{"kind":"Field","name":{"kind":"Name","value":"total"}},{"kind":"Field","name":{"kind":"Name","value":"pending"}},{"kind":"Field","name":{"kind":"Name","value":"annotated"}},{"kind":"Field","name":{"kind":"Name","value":"avgRqi"}},{"kind":"Field","name":{"kind":"Name","value":"goodCount"}},{"kind":"Field","name":{"kind":"Name","value":"fairCount"}},{"kind":"Field","name":{"kind":"Name","value":"poorCount"}},{"kind":"Field","name":{"kind":"Name","value":"pendingAnalysis"}},{"kind":"Field","name":{"kind":"Name","value":"rqi1Count"}},{"kind":"Field","name":{"kind":"Name","value":"rqi2Count"}},{"kind":"Field","name":{"kind":"Name","value":"rqi3Count"}},{"kind":"Field","name":{"kind":"Name","value":"rqi4Count"}},{"kind":"Field","name":{"kind":"Name","value":"rqi5Count"}}]}}]}}]} as unknown as DocumentNode<GetTrainingStatsQuery, GetTrainingStatsQueryVariables>;
export const RunAnalysisDocument = {"kind":"Document","definitions":[{"kind":"OperationDefinition","operation":"mutation","name":{"kind":"Name","value":"RunAnalysis"},"variableDefinitions":[{"kind":"VariableDefinition","variable":{"kind":"Variable","name":{"kind":"Name","value":"input"}},"type":{"kind":"NonNullType","type":{"kind":"NamedType","name":{"kind":"Name","value":"RunAnalysisInput"}}}}],"selectionSet":{"kind":"SelectionSet","selections":[{"kind":"Field","name":{"kind":"Name","value":"runAnalysis"},"arguments":[{"kind":"Argument","name":{"kind":"Name","value":"input"},"value":{"kind":"Variable","name":{"kind":"Name","value":"input"}}}],"selectionSet":{"kind":"SelectionSet","selections":[{"kind":"Field","name":{"kind":"Name","value":"id"}}]}}]}}]} as unknown as DocumentNode<RunAnalysisMutation, RunAnalysisMutationVariables>;
export const StartModelTrainingDocument = {"kind":"Document","definitions":[{"kind":"OperationDefinition","operation":"mutation","name":{"kind":"Name","value":"StartModelTraining"},"selectionSet":{"kind":"SelectionSet","selections":[{"kind":"Field","name":{"kind":"Name","value":"startModelTraining"},"selectionSet":{"kind":"SelectionSet","selections":[{"kind":"Field","name":{"kind":"Name","value":"id"}}]}}]}}]} as unknown as DocumentNode<StartModelTrainingMutation, StartModelTrainingMutationVariables>;
export const StopJobDocument = {"kind":"Document","definitions":[{"kind":"OperationDefinition","operation":"mutation","name":{"kind":"Name","value":"StopJob"},"variableDefinitions":[{"kind":"VariableDefinition","variable":{"kind":"Variable","name":{"kind":"Name","value":"jobId"}},"type":{"kind":"NonNullType","type":{"kind":"NamedType","name":{"kind":"Name","value":"String"}}}}],"selectionSet":{"kind":"SelectionSet","selections":[{"kind":"Field","name":{"kind":"Name","value":"stopJob"},"arguments":[{"kind":"Argument","name":{"kind":"Name","value":"jobId"},"value":{"kind":"Variable","name":{"kind":"Name","value":"jobId"}}}]}]}}]} as unknown as DocumentNode<StopJobMutation, StopJobMutationVariables>;
export const PerformReviewActionDocument = {"kind":"Document","definitions":[{"kind":"OperationDefinition","operation":"mutation","name":{"kind":"Name","value":"PerformReviewAction"},"variableDefinitions":[{"kind":"VariableDefinition","variable":{"kind":"Variable","name":{"kind":"Name","value":"input"}},"type":{"kind":"NonNullType","type":{"kind":"NamedType","name":{"kind":"Name","value":"ReviewActionInput"}}}}],"selectionSet":{"kind":"SelectionSet","selections":[{"kind":"Field","name":{"kind":"Name","value":"performReviewAction"},"arguments":[{"kind":"Argument","name":{"kind":"Name","value":"input"},"value":{"kind":"Variable","name":{"kind":"Name","value":"input"}}}],"selectionSet":{"kind":"SelectionSet","selections":[{"kind":"Field","name":{"kind":"Name","value":"success"}},{"kind":"Field","name":{"kind":"Name","value":"message"}},{"kind":"Field","name":{"kind":"Name","value":"processedImageUrl"}},{"kind":"Field","name":{"kind":"Name","value":"annotations"},"selectionSet":{"kind":"SelectionSet","selections":[{"kind":"Field","name":{"kind":"Name","value":"id"}},{"kind":"Field","name":{"kind":"Name","value":"label"}},{"kind":"Field","name":{"kind":"Name","value":"score"}},{"kind":"Field","name":{"kind":"Name","value":"type"}},{"kind":"Field","name":{"kind":"Name","value":"points"}}]}}]}}]}}]} as unknown as DocumentNode<PerformReviewActionMutation, PerformReviewActionMutationVariables>;