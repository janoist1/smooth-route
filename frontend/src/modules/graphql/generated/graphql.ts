/* eslint-disable */
/** Internal type. DO NOT USE DIRECTLY. */
type Exact<T extends { [key: string]: unknown }> = { [K in keyof T]: T[K] };
/** Internal type. DO NOT USE DIRECTLY. */
export type Incremental<T> = T | { [P in keyof T]?: P extends ' $fragmentName' | '__typename' ? T[P] : never };
import type { TypedDocumentNode as DocumentNode } from '@graphql-typed-document-node/core';
export type FilterMode =
  | 'ALL'
  | 'PENDING'
  | 'REVIEWED';

export type LabelQueueStrategy =
  | 'DIVERSE'
  | 'MIXED'
  | 'RECHECK'
  | 'SPRINT'
  | 'UNCERTAIN';

export type PairJudgmentInput = {
  clientId: string;
  elapsedMs?: number | null | undefined;
  frameAId: number;
  frameBId: number;
  result: PairResult;
};

export type PairResult =
  | 'A'
  | 'B'
  | 'EQUAL';

export type ProcessRouteInput = {
  destination: string;
  origin: string;
};

export type QuickLabelInput = {
  elapsedMs?: number | null | undefined;
  pointId: number;
  reason?: string | null | undefined;
  revealedModel?: boolean;
  rqi: number;
  strategy?: string | null | undefined;
};

export type ReviewActionInput = {
  actionType: string;
  parameters: unknown;
};

export type RunAnalysisInput = {
  limit?: number;
  reanalyze?: boolean;
  strategy: string;
};

export type TrainingDataInput = {
  annotations?: unknown;
  imageFilename: string;
  manualComment?: string | null | undefined;
  manualRqi?: number | null | undefined;
  metaData?: unknown;
  tags?: Array<string> | null | undefined;
};

export type UpdateSettingInput = {
  key: string;
  value: unknown;
};

export type AdminStatsQueryVariables = Exact<{ [key: string]: never; }>;


export type AdminStatsQuery = { adminStats: { totalImages: number, imagesThisMonth: number, freeTierLimit: number, billableThisMonth: number, totalPoints: number, analyzedPoints: number, pendingAnalysis: number, rqiGood: number, rqiFair: number, rqiPoor: number, totalUsers: number, adminUsers: number, imagesPerDay: Array<{ day: string, count: number }>, recentJobs: Array<{ id: string, status: string, message: string | null, progress: number, total: number }> } };

export type GetJobQueryVariables = Exact<{
  id: string;
}>;


export type GetJobQuery = { job: { id: string, status: string, progress: number, total: number, message: string, result: unknown, error: string | null, createdAt: unknown, completedAt: unknown } | null };

export type ViewerQueryVariables = Exact<{ [key: string]: never; }>;


export type ViewerQuery = { me: { clerkId: string, email: string | null, role: string } | null };

export type LabelQueueQueryVariables = Exact<{
  strategy: LabelQueueStrategy;
  limit: number;
  excludeIds?: Array<number> | number | null | undefined;
}>;


export type LabelQueueQuery = { labelQueue: { strategy: LabelQueueStrategy, items: Array<{ id: number, imageUrl: string, latitude: number, longitude: number, heading: number | null, captureDate: string | null, streetViewUrl: string, reason: string, area: string, uncertainty: number | null, cellLabels: number, boundary: string | null, modelScore: number | null, modelRqi: number | null, modelPBad: number | null }>, stats: { totalLabelled: number, labelledToday: number, eligible: number, scored: number, rechecked: number, recheckSame: number | null, recheckWithinOne: number | null, sprintLabelled: number, sprintTarget: number } } };

export type PairQueueQueryVariables = Exact<{
  limit: number;
  excludeIds?: Array<number> | number | null | undefined;
}>;


export type PairQueueQuery = { pairQueue: { judged: number, pairs: Array<{ scoreGap: number, a: { id: number, imageUrl: string, latitude: number, longitude: number, heading: number | null, captureDate: string | null, streetViewUrl: string, reason: string, area: string, uncertainty: number | null, cellLabels: number, boundary: string | null, modelScore: number | null, modelRqi: number | null, modelPBad: number | null }, b: { id: number, imageUrl: string, latitude: number, longitude: number, heading: number | null, captureDate: string | null, streetViewUrl: string, reason: string, area: string, uncertainty: number | null, cellLabels: number, boundary: string | null, modelScore: number | null, modelRqi: number | null, modelPBad: number | null } }> } };

export type SubmitPairJudgmentMutationVariables = Exact<{
  input: PairJudgmentInput;
}>;


export type SubmitPairJudgmentMutation = { submitPairJudgment: boolean };

export type UndoPairJudgmentMutationVariables = Exact<{
  clientId: string;
}>;


export type UndoPairJudgmentMutation = { undoPairJudgment: boolean };

export type LabelExamplesQueryVariables = Exact<{
  perClass: number;
}>;


export type LabelExamplesQuery = { labelExamples: Array<{ rqi: number, id: number, imageUrl: string }> };

export type QuickLabelMutationVariables = Exact<{
  input: QuickLabelInput;
}>;


export type QuickLabelMutation = { quickLabel: { pointId: number, rqi: number, totalLabelled: number, labelledToday: number } };

export type UndoQuickLabelMutationVariables = Exact<{
  pointId: number;
}>;


export type UndoQuickLabelMutation = { undoQuickLabel: boolean };

export type GetPointsQueryVariables = Exact<{
  limit?: number | null | undefined;
  bbox?: Array<number> | number | null | undefined;
}>;


export type GetPointsQuery = { points: Array<{ id: number, latitude: number, longitude: number, rqiScore: number | null, dinoRqiScore: number | null, rqiSource: string, heading: number, captureDate: string | null }> };

export type GetRoadQualityGridQueryVariables = Exact<{
  zoom: number;
  bbox?: Array<number> | number | null | undefined;
}>;


export type GetRoadQualityGridQuery = { roadQualityGrid: unknown };

export type GetPointDetailQueryVariables = Exact<{
  id: number;
}>;


export type GetPointDetailQuery = { point: { id: number, latitude: number, longitude: number, rqiScore: number | null, dinoRqiScore: number | null, dinoScore: number | null, dinoPBad: number | null, rqiSource: string, heading: number, pitch: number | null, imageUrl: string | null, streetViewUrl: string, captureDate: string | null, manualRqi: number | null, manualTags: Array<string> | null, manualAnnotations: unknown, damageCount: number, damageTypes: unknown, analysisMetadata: unknown, createdAt: unknown } | null };

export type RouteAlternativesQueryVariables = Exact<{
  origin: string;
  destination: string;
}>;


export type RouteAlternativesQuery = { routeAlternatives: { fastestIndex: number | null, smoothestIndex: number | null, routes: Array<{ index: number, distanceM: number, durationS: number, summary: string, coverage: number, isFastest: boolean, isSmoothest: boolean, points: Array<{ lat: number, lng: number }>, quality: { totalLengthM: number, coveredLengthM: number, lengthByRqi: Array<number>, meanScore: number | null, impactScore: number | null } }> } };

export type ProcessRouteMutationVariables = Exact<{
  input: ProcessRouteInput;
}>;


export type ProcessRouteMutation = { processRoute: { id: string, status: string, message: string } };

export type GetActiveJobQueryVariables = Exact<{ [key: string]: never; }>;


export type GetActiveJobQuery = { activeJob: { id: string, type: string, status: string, progress: number, total: number, details: unknown, result: unknown } | null };

export type GetRoadSegmentsQueryVariables = Exact<{
  bbox: Array<number> | number;
  zoom: number;
}>;


export type GetRoadSegmentsQuery = { roadSegments: Array<{ id: string, path: Array<Array<number>>, rqi: number | null, score: number | null, pBad: number | null, confidence: number, confidenceLevel: string, confidenceReason: string | null, nImages: number, lengthM: number, roadName: string | null, highway: string | null, captureDateMin: string | null, captureDateMax: string | null }> };

export type GetRouteQualityQueryVariables = Exact<{
  path: Array<Array<number> | number> | Array<number> | number;
}>;


export type GetRouteQualityQuery = { routeQuality: { totalLengthM: number, coveredLengthM: number, lengthByRqi: Array<number>, meanScore: number | null, worstSegments: Array<{ id: string, path: Array<Array<number>>, rqi: number | null, score: number | null, pBad: number | null, confidence: number, confidenceLevel: string, confidenceReason: string | null, nImages: number, lengthM: number, roadName: string | null, highway: string | null, captureDateMin: string | null, captureDateMax: string | null }> } };

export type GetSegmentFramesQueryVariables = Exact<{
  limit?: number | null | undefined;
  bbox?: Array<number> | number | null | undefined;
}>;


export type GetSegmentFramesQuery = { points: Array<{ id: number, latitude: number, longitude: number, rqiScore: number | null, rqiSource: string, heading: number, captureDate: string | null }> };

export type GetAvailableModelsQueryVariables = Exact<{ [key: string]: never; }>;


export type GetAvailableModelsQuery = { availableModels: Array<string> };

export type GetSettingsQueryVariables = Exact<{ [key: string]: never; }>;


export type GetSettingsQuery = { settings: Array<{ key: string, value: unknown, description: string | null, example: string | null, category: string | null, explanation: string | null }> };

export type UpdateSettingMutationVariables = Exact<{
  input: UpdateSettingInput;
}>;


export type UpdateSettingMutation = { updateSetting: { key: string, value: unknown, description: string | null, example: string | null, category: string | null, explanation: string | null } };

export type GetRqiModelInfoQueryVariables = Exact<{ [key: string]: never; }>;


export type GetRqiModelInfoQuery = { rqiModelInfo: { available: boolean, version: number | null, backbone: string | null, recipe: string | null, head: string | null, nTrain: number | null, qwk: number | null, mae: number | null, exactAcc: number | null, badRoadAcc: number | null, badRoadAuc: number | null, scaleMeaning: string | null, metricsSource: string | null, metricsProtocol: string | null, metricsMeasuredOn: string | null, segmentQwk: number | null, segmentLengthM: number | null, newAreaQwk: number | null } };

export type GetTrainingDataQueryVariables = Exact<{
  id: number;
}>;


export type GetTrainingDataQuery = { point: { imageUrl: string | null, manualRqi: number | null, manualTags: Array<string> | null, manualAnnotations: unknown, manualComment: string | null } | null };

export type SaveTrainingDataMutationVariables = Exact<{
  input: TrainingDataInput;
}>;


export type SaveTrainingDataMutation = { saveTrainingData: string };

export type DeleteTrainingDataMutationVariables = Exact<{
  imageFilename: string;
}>;


export type DeleteTrainingDataMutation = { deleteTrainingData: boolean };

export type GetTrainingPointsQueryVariables = Exact<{
  mode?: FilterMode | null | undefined;
  limit?: number | null | undefined;
  offset?: number | null | undefined;
  model?: string | null | undefined;
}>;


export type GetTrainingPointsQuery = { trainingPoints: { totalCount: number, hasMore: boolean, items: Array<{ id: number, latitude: number, longitude: number, imageUrl: string | null, rqiScore: number | null, dinoRqiScore: number | null, manualRqi: number | null }> } };

export type GetTrainingStatsQueryVariables = Exact<{
  mode?: FilterMode | null | undefined;
  isDino?: boolean | null | undefined;
}>;


export type GetTrainingStatsQuery = { trainingStats: { total: number, pending: number, annotated: number, avgRqi: number, goodCount: number, fairCount: number, poorCount: number, pendingAnalysis: number, rqi1Count: number, rqi2Count: number, rqi3Count: number, rqi4Count: number, rqi5Count: number } };

export type RunAnalysisMutationVariables = Exact<{
  input: RunAnalysisInput;
}>;


export type RunAnalysisMutation = { runAnalysis: { id: string } };

export type StartModelTrainingMutationVariables = Exact<{ [key: string]: never; }>;


export type StartModelTrainingMutation = { startModelTraining: { id: string } };

export type StopJobMutationVariables = Exact<{
  jobId: string;
}>;


export type StopJobMutation = { stopJob: boolean };

export type PerformReviewActionMutationVariables = Exact<{
  input: ReviewActionInput;
}>;


export type PerformReviewActionMutation = { performReviewAction: { success: boolean, message: string | null, processedImageUrl: string | null, annotations: Array<{ id: string, label: string, score: number, type: string, points: unknown }> | null } };


export const AdminStatsDocument = {"kind":"Document","definitions":[{"kind":"OperationDefinition","operation":"query","name":{"kind":"Name","value":"AdminStats"},"selectionSet":{"kind":"SelectionSet","selections":[{"kind":"Field","name":{"kind":"Name","value":"adminStats"},"selectionSet":{"kind":"SelectionSet","selections":[{"kind":"Field","name":{"kind":"Name","value":"totalImages"}},{"kind":"Field","name":{"kind":"Name","value":"imagesThisMonth"}},{"kind":"Field","name":{"kind":"Name","value":"freeTierLimit"}},{"kind":"Field","name":{"kind":"Name","value":"billableThisMonth"}},{"kind":"Field","name":{"kind":"Name","value":"totalPoints"}},{"kind":"Field","name":{"kind":"Name","value":"analyzedPoints"}},{"kind":"Field","name":{"kind":"Name","value":"pendingAnalysis"}},{"kind":"Field","name":{"kind":"Name","value":"rqiGood"}},{"kind":"Field","name":{"kind":"Name","value":"rqiFair"}},{"kind":"Field","name":{"kind":"Name","value":"rqiPoor"}},{"kind":"Field","name":{"kind":"Name","value":"totalUsers"}},{"kind":"Field","name":{"kind":"Name","value":"adminUsers"}},{"kind":"Field","name":{"kind":"Name","value":"imagesPerDay"},"selectionSet":{"kind":"SelectionSet","selections":[{"kind":"Field","name":{"kind":"Name","value":"day"}},{"kind":"Field","name":{"kind":"Name","value":"count"}}]}},{"kind":"Field","name":{"kind":"Name","value":"recentJobs"},"selectionSet":{"kind":"SelectionSet","selections":[{"kind":"Field","name":{"kind":"Name","value":"id"}},{"kind":"Field","name":{"kind":"Name","value":"status"}},{"kind":"Field","name":{"kind":"Name","value":"message"}},{"kind":"Field","name":{"kind":"Name","value":"progress"}},{"kind":"Field","name":{"kind":"Name","value":"total"}}]}}]}}]}}]} as unknown as DocumentNode<AdminStatsQuery, AdminStatsQueryVariables>;
export const GetJobDocument = {"kind":"Document","definitions":[{"kind":"OperationDefinition","operation":"query","name":{"kind":"Name","value":"GetJob"},"variableDefinitions":[{"kind":"VariableDefinition","variable":{"kind":"Variable","name":{"kind":"Name","value":"id"}},"type":{"kind":"NonNullType","type":{"kind":"NamedType","name":{"kind":"Name","value":"String"}}}}],"selectionSet":{"kind":"SelectionSet","selections":[{"kind":"Field","name":{"kind":"Name","value":"job"},"arguments":[{"kind":"Argument","name":{"kind":"Name","value":"id"},"value":{"kind":"Variable","name":{"kind":"Name","value":"id"}}}],"selectionSet":{"kind":"SelectionSet","selections":[{"kind":"Field","name":{"kind":"Name","value":"id"}},{"kind":"Field","name":{"kind":"Name","value":"status"}},{"kind":"Field","name":{"kind":"Name","value":"progress"}},{"kind":"Field","name":{"kind":"Name","value":"total"}},{"kind":"Field","name":{"kind":"Name","value":"message"}},{"kind":"Field","name":{"kind":"Name","value":"result"}},{"kind":"Field","name":{"kind":"Name","value":"error"}},{"kind":"Field","name":{"kind":"Name","value":"createdAt"}},{"kind":"Field","name":{"kind":"Name","value":"completedAt"}}]}}]}}]} as unknown as DocumentNode<GetJobQuery, GetJobQueryVariables>;
export const ViewerDocument = {"kind":"Document","definitions":[{"kind":"OperationDefinition","operation":"query","name":{"kind":"Name","value":"Viewer"},"selectionSet":{"kind":"SelectionSet","selections":[{"kind":"Field","name":{"kind":"Name","value":"me"},"selectionSet":{"kind":"SelectionSet","selections":[{"kind":"Field","name":{"kind":"Name","value":"clerkId"}},{"kind":"Field","name":{"kind":"Name","value":"email"}},{"kind":"Field","name":{"kind":"Name","value":"role"}}]}}]}}]} as unknown as DocumentNode<ViewerQuery, ViewerQueryVariables>;
export const LabelQueueDocument = {"kind":"Document","definitions":[{"kind":"OperationDefinition","operation":"query","name":{"kind":"Name","value":"LabelQueue"},"variableDefinitions":[{"kind":"VariableDefinition","variable":{"kind":"Variable","name":{"kind":"Name","value":"strategy"}},"type":{"kind":"NonNullType","type":{"kind":"NamedType","name":{"kind":"Name","value":"LabelQueueStrategy"}}}},{"kind":"VariableDefinition","variable":{"kind":"Variable","name":{"kind":"Name","value":"limit"}},"type":{"kind":"NonNullType","type":{"kind":"NamedType","name":{"kind":"Name","value":"Int"}}}},{"kind":"VariableDefinition","variable":{"kind":"Variable","name":{"kind":"Name","value":"excludeIds"}},"type":{"kind":"ListType","type":{"kind":"NonNullType","type":{"kind":"NamedType","name":{"kind":"Name","value":"Int"}}}}}],"selectionSet":{"kind":"SelectionSet","selections":[{"kind":"Field","name":{"kind":"Name","value":"labelQueue"},"arguments":[{"kind":"Argument","name":{"kind":"Name","value":"strategy"},"value":{"kind":"Variable","name":{"kind":"Name","value":"strategy"}}},{"kind":"Argument","name":{"kind":"Name","value":"limit"},"value":{"kind":"Variable","name":{"kind":"Name","value":"limit"}}},{"kind":"Argument","name":{"kind":"Name","value":"excludeIds"},"value":{"kind":"Variable","name":{"kind":"Name","value":"excludeIds"}}}],"selectionSet":{"kind":"SelectionSet","selections":[{"kind":"Field","name":{"kind":"Name","value":"strategy"}},{"kind":"Field","name":{"kind":"Name","value":"items"},"selectionSet":{"kind":"SelectionSet","selections":[{"kind":"Field","name":{"kind":"Name","value":"id"}},{"kind":"Field","name":{"kind":"Name","value":"imageUrl"}},{"kind":"Field","name":{"kind":"Name","value":"latitude"}},{"kind":"Field","name":{"kind":"Name","value":"longitude"}},{"kind":"Field","name":{"kind":"Name","value":"heading"}},{"kind":"Field","name":{"kind":"Name","value":"captureDate"}},{"kind":"Field","name":{"kind":"Name","value":"streetViewUrl"}},{"kind":"Field","name":{"kind":"Name","value":"reason"}},{"kind":"Field","name":{"kind":"Name","value":"area"}},{"kind":"Field","name":{"kind":"Name","value":"uncertainty"}},{"kind":"Field","name":{"kind":"Name","value":"cellLabels"}},{"kind":"Field","name":{"kind":"Name","value":"boundary"}},{"kind":"Field","name":{"kind":"Name","value":"modelScore"}},{"kind":"Field","name":{"kind":"Name","value":"modelRqi"}},{"kind":"Field","name":{"kind":"Name","value":"modelPBad"}}]}},{"kind":"Field","name":{"kind":"Name","value":"stats"},"selectionSet":{"kind":"SelectionSet","selections":[{"kind":"Field","name":{"kind":"Name","value":"totalLabelled"}},{"kind":"Field","name":{"kind":"Name","value":"labelledToday"}},{"kind":"Field","name":{"kind":"Name","value":"eligible"}},{"kind":"Field","name":{"kind":"Name","value":"scored"}},{"kind":"Field","name":{"kind":"Name","value":"rechecked"}},{"kind":"Field","name":{"kind":"Name","value":"recheckSame"}},{"kind":"Field","name":{"kind":"Name","value":"recheckWithinOne"}},{"kind":"Field","name":{"kind":"Name","value":"sprintLabelled"}},{"kind":"Field","name":{"kind":"Name","value":"sprintTarget"}}]}}]}}]}}]} as unknown as DocumentNode<LabelQueueQuery, LabelQueueQueryVariables>;
export const PairQueueDocument = {"kind":"Document","definitions":[{"kind":"OperationDefinition","operation":"query","name":{"kind":"Name","value":"PairQueue"},"variableDefinitions":[{"kind":"VariableDefinition","variable":{"kind":"Variable","name":{"kind":"Name","value":"limit"}},"type":{"kind":"NonNullType","type":{"kind":"NamedType","name":{"kind":"Name","value":"Int"}}}},{"kind":"VariableDefinition","variable":{"kind":"Variable","name":{"kind":"Name","value":"excludeIds"}},"type":{"kind":"ListType","type":{"kind":"NonNullType","type":{"kind":"NamedType","name":{"kind":"Name","value":"Int"}}}}}],"selectionSet":{"kind":"SelectionSet","selections":[{"kind":"Field","name":{"kind":"Name","value":"pairQueue"},"arguments":[{"kind":"Argument","name":{"kind":"Name","value":"limit"},"value":{"kind":"Variable","name":{"kind":"Name","value":"limit"}}},{"kind":"Argument","name":{"kind":"Name","value":"excludeIds"},"value":{"kind":"Variable","name":{"kind":"Name","value":"excludeIds"}}}],"selectionSet":{"kind":"SelectionSet","selections":[{"kind":"Field","name":{"kind":"Name","value":"judged"}},{"kind":"Field","name":{"kind":"Name","value":"pairs"},"selectionSet":{"kind":"SelectionSet","selections":[{"kind":"Field","name":{"kind":"Name","value":"scoreGap"}},{"kind":"Field","name":{"kind":"Name","value":"a"},"selectionSet":{"kind":"SelectionSet","selections":[{"kind":"Field","name":{"kind":"Name","value":"id"}},{"kind":"Field","name":{"kind":"Name","value":"imageUrl"}},{"kind":"Field","name":{"kind":"Name","value":"latitude"}},{"kind":"Field","name":{"kind":"Name","value":"longitude"}},{"kind":"Field","name":{"kind":"Name","value":"heading"}},{"kind":"Field","name":{"kind":"Name","value":"captureDate"}},{"kind":"Field","name":{"kind":"Name","value":"streetViewUrl"}},{"kind":"Field","name":{"kind":"Name","value":"reason"}},{"kind":"Field","name":{"kind":"Name","value":"area"}},{"kind":"Field","name":{"kind":"Name","value":"uncertainty"}},{"kind":"Field","name":{"kind":"Name","value":"cellLabels"}},{"kind":"Field","name":{"kind":"Name","value":"boundary"}},{"kind":"Field","name":{"kind":"Name","value":"modelScore"}},{"kind":"Field","name":{"kind":"Name","value":"modelRqi"}},{"kind":"Field","name":{"kind":"Name","value":"modelPBad"}}]}},{"kind":"Field","name":{"kind":"Name","value":"b"},"selectionSet":{"kind":"SelectionSet","selections":[{"kind":"Field","name":{"kind":"Name","value":"id"}},{"kind":"Field","name":{"kind":"Name","value":"imageUrl"}},{"kind":"Field","name":{"kind":"Name","value":"latitude"}},{"kind":"Field","name":{"kind":"Name","value":"longitude"}},{"kind":"Field","name":{"kind":"Name","value":"heading"}},{"kind":"Field","name":{"kind":"Name","value":"captureDate"}},{"kind":"Field","name":{"kind":"Name","value":"streetViewUrl"}},{"kind":"Field","name":{"kind":"Name","value":"reason"}},{"kind":"Field","name":{"kind":"Name","value":"area"}},{"kind":"Field","name":{"kind":"Name","value":"uncertainty"}},{"kind":"Field","name":{"kind":"Name","value":"cellLabels"}},{"kind":"Field","name":{"kind":"Name","value":"boundary"}},{"kind":"Field","name":{"kind":"Name","value":"modelScore"}},{"kind":"Field","name":{"kind":"Name","value":"modelRqi"}},{"kind":"Field","name":{"kind":"Name","value":"modelPBad"}}]}}]}}]}}]}}]} as unknown as DocumentNode<PairQueueQuery, PairQueueQueryVariables>;
export const SubmitPairJudgmentDocument = {"kind":"Document","definitions":[{"kind":"OperationDefinition","operation":"mutation","name":{"kind":"Name","value":"SubmitPairJudgment"},"variableDefinitions":[{"kind":"VariableDefinition","variable":{"kind":"Variable","name":{"kind":"Name","value":"input"}},"type":{"kind":"NonNullType","type":{"kind":"NamedType","name":{"kind":"Name","value":"PairJudgmentInput"}}}}],"selectionSet":{"kind":"SelectionSet","selections":[{"kind":"Field","name":{"kind":"Name","value":"submitPairJudgment"},"arguments":[{"kind":"Argument","name":{"kind":"Name","value":"input"},"value":{"kind":"Variable","name":{"kind":"Name","value":"input"}}}]}]}}]} as unknown as DocumentNode<SubmitPairJudgmentMutation, SubmitPairJudgmentMutationVariables>;
export const UndoPairJudgmentDocument = {"kind":"Document","definitions":[{"kind":"OperationDefinition","operation":"mutation","name":{"kind":"Name","value":"UndoPairJudgment"},"variableDefinitions":[{"kind":"VariableDefinition","variable":{"kind":"Variable","name":{"kind":"Name","value":"clientId"}},"type":{"kind":"NonNullType","type":{"kind":"NamedType","name":{"kind":"Name","value":"String"}}}}],"selectionSet":{"kind":"SelectionSet","selections":[{"kind":"Field","name":{"kind":"Name","value":"undoPairJudgment"},"arguments":[{"kind":"Argument","name":{"kind":"Name","value":"clientId"},"value":{"kind":"Variable","name":{"kind":"Name","value":"clientId"}}}]}]}}]} as unknown as DocumentNode<UndoPairJudgmentMutation, UndoPairJudgmentMutationVariables>;
export const LabelExamplesDocument = {"kind":"Document","definitions":[{"kind":"OperationDefinition","operation":"query","name":{"kind":"Name","value":"LabelExamples"},"variableDefinitions":[{"kind":"VariableDefinition","variable":{"kind":"Variable","name":{"kind":"Name","value":"perClass"}},"type":{"kind":"NonNullType","type":{"kind":"NamedType","name":{"kind":"Name","value":"Int"}}}}],"selectionSet":{"kind":"SelectionSet","selections":[{"kind":"Field","name":{"kind":"Name","value":"labelExamples"},"arguments":[{"kind":"Argument","name":{"kind":"Name","value":"perClass"},"value":{"kind":"Variable","name":{"kind":"Name","value":"perClass"}}}],"selectionSet":{"kind":"SelectionSet","selections":[{"kind":"Field","name":{"kind":"Name","value":"rqi"}},{"kind":"Field","name":{"kind":"Name","value":"id"}},{"kind":"Field","name":{"kind":"Name","value":"imageUrl"}}]}}]}}]} as unknown as DocumentNode<LabelExamplesQuery, LabelExamplesQueryVariables>;
export const QuickLabelDocument = {"kind":"Document","definitions":[{"kind":"OperationDefinition","operation":"mutation","name":{"kind":"Name","value":"QuickLabel"},"variableDefinitions":[{"kind":"VariableDefinition","variable":{"kind":"Variable","name":{"kind":"Name","value":"input"}},"type":{"kind":"NonNullType","type":{"kind":"NamedType","name":{"kind":"Name","value":"QuickLabelInput"}}}}],"selectionSet":{"kind":"SelectionSet","selections":[{"kind":"Field","name":{"kind":"Name","value":"quickLabel"},"arguments":[{"kind":"Argument","name":{"kind":"Name","value":"input"},"value":{"kind":"Variable","name":{"kind":"Name","value":"input"}}}],"selectionSet":{"kind":"SelectionSet","selections":[{"kind":"Field","name":{"kind":"Name","value":"pointId"}},{"kind":"Field","name":{"kind":"Name","value":"rqi"}},{"kind":"Field","name":{"kind":"Name","value":"totalLabelled"}},{"kind":"Field","name":{"kind":"Name","value":"labelledToday"}}]}}]}}]} as unknown as DocumentNode<QuickLabelMutation, QuickLabelMutationVariables>;
export const UndoQuickLabelDocument = {"kind":"Document","definitions":[{"kind":"OperationDefinition","operation":"mutation","name":{"kind":"Name","value":"UndoQuickLabel"},"variableDefinitions":[{"kind":"VariableDefinition","variable":{"kind":"Variable","name":{"kind":"Name","value":"pointId"}},"type":{"kind":"NonNullType","type":{"kind":"NamedType","name":{"kind":"Name","value":"Int"}}}}],"selectionSet":{"kind":"SelectionSet","selections":[{"kind":"Field","name":{"kind":"Name","value":"undoQuickLabel"},"arguments":[{"kind":"Argument","name":{"kind":"Name","value":"pointId"},"value":{"kind":"Variable","name":{"kind":"Name","value":"pointId"}}}]}]}}]} as unknown as DocumentNode<UndoQuickLabelMutation, UndoQuickLabelMutationVariables>;
export const GetPointsDocument = {"kind":"Document","definitions":[{"kind":"OperationDefinition","operation":"query","name":{"kind":"Name","value":"GetPoints"},"variableDefinitions":[{"kind":"VariableDefinition","variable":{"kind":"Variable","name":{"kind":"Name","value":"limit"}},"type":{"kind":"NamedType","name":{"kind":"Name","value":"Int"}}},{"kind":"VariableDefinition","variable":{"kind":"Variable","name":{"kind":"Name","value":"bbox"}},"type":{"kind":"ListType","type":{"kind":"NonNullType","type":{"kind":"NamedType","name":{"kind":"Name","value":"Float"}}}}}],"selectionSet":{"kind":"SelectionSet","selections":[{"kind":"Field","name":{"kind":"Name","value":"points"},"arguments":[{"kind":"Argument","name":{"kind":"Name","value":"limit"},"value":{"kind":"Variable","name":{"kind":"Name","value":"limit"}}},{"kind":"Argument","name":{"kind":"Name","value":"bbox"},"value":{"kind":"Variable","name":{"kind":"Name","value":"bbox"}}}],"selectionSet":{"kind":"SelectionSet","selections":[{"kind":"Field","name":{"kind":"Name","value":"id"}},{"kind":"Field","name":{"kind":"Name","value":"latitude"}},{"kind":"Field","name":{"kind":"Name","value":"longitude"}},{"kind":"Field","name":{"kind":"Name","value":"rqiScore"}},{"kind":"Field","name":{"kind":"Name","value":"dinoRqiScore"}},{"kind":"Field","name":{"kind":"Name","value":"rqiSource"}},{"kind":"Field","name":{"kind":"Name","value":"heading"}},{"kind":"Field","name":{"kind":"Name","value":"captureDate"}}]}}]}}]} as unknown as DocumentNode<GetPointsQuery, GetPointsQueryVariables>;
export const GetRoadQualityGridDocument = {"kind":"Document","definitions":[{"kind":"OperationDefinition","operation":"query","name":{"kind":"Name","value":"GetRoadQualityGrid"},"variableDefinitions":[{"kind":"VariableDefinition","variable":{"kind":"Variable","name":{"kind":"Name","value":"zoom"}},"type":{"kind":"NonNullType","type":{"kind":"NamedType","name":{"kind":"Name","value":"Int"}}}},{"kind":"VariableDefinition","variable":{"kind":"Variable","name":{"kind":"Name","value":"bbox"}},"type":{"kind":"ListType","type":{"kind":"NonNullType","type":{"kind":"NamedType","name":{"kind":"Name","value":"Float"}}}}}],"selectionSet":{"kind":"SelectionSet","selections":[{"kind":"Field","name":{"kind":"Name","value":"roadQualityGrid"},"arguments":[{"kind":"Argument","name":{"kind":"Name","value":"zoom"},"value":{"kind":"Variable","name":{"kind":"Name","value":"zoom"}}},{"kind":"Argument","name":{"kind":"Name","value":"bbox"},"value":{"kind":"Variable","name":{"kind":"Name","value":"bbox"}}}]}]}}]} as unknown as DocumentNode<GetRoadQualityGridQuery, GetRoadQualityGridQueryVariables>;
export const GetPointDetailDocument = {"kind":"Document","definitions":[{"kind":"OperationDefinition","operation":"query","name":{"kind":"Name","value":"GetPointDetail"},"variableDefinitions":[{"kind":"VariableDefinition","variable":{"kind":"Variable","name":{"kind":"Name","value":"id"}},"type":{"kind":"NonNullType","type":{"kind":"NamedType","name":{"kind":"Name","value":"Int"}}}}],"selectionSet":{"kind":"SelectionSet","selections":[{"kind":"Field","name":{"kind":"Name","value":"point"},"arguments":[{"kind":"Argument","name":{"kind":"Name","value":"id"},"value":{"kind":"Variable","name":{"kind":"Name","value":"id"}}}],"selectionSet":{"kind":"SelectionSet","selections":[{"kind":"Field","name":{"kind":"Name","value":"id"}},{"kind":"Field","name":{"kind":"Name","value":"latitude"}},{"kind":"Field","name":{"kind":"Name","value":"longitude"}},{"kind":"Field","name":{"kind":"Name","value":"rqiScore"}},{"kind":"Field","name":{"kind":"Name","value":"dinoRqiScore"}},{"kind":"Field","name":{"kind":"Name","value":"dinoScore"}},{"kind":"Field","name":{"kind":"Name","value":"dinoPBad"}},{"kind":"Field","name":{"kind":"Name","value":"rqiSource"}},{"kind":"Field","name":{"kind":"Name","value":"heading"}},{"kind":"Field","name":{"kind":"Name","value":"pitch"}},{"kind":"Field","name":{"kind":"Name","value":"imageUrl"}},{"kind":"Field","name":{"kind":"Name","value":"streetViewUrl"}},{"kind":"Field","name":{"kind":"Name","value":"captureDate"}},{"kind":"Field","name":{"kind":"Name","value":"manualRqi"}},{"kind":"Field","name":{"kind":"Name","value":"manualTags"}},{"kind":"Field","name":{"kind":"Name","value":"manualAnnotations"}},{"kind":"Field","name":{"kind":"Name","value":"damageCount"}},{"kind":"Field","name":{"kind":"Name","value":"damageTypes"}},{"kind":"Field","name":{"kind":"Name","value":"analysisMetadata"}},{"kind":"Field","name":{"kind":"Name","value":"createdAt"}}]}}]}}]} as unknown as DocumentNode<GetPointDetailQuery, GetPointDetailQueryVariables>;
export const RouteAlternativesDocument = {"kind":"Document","definitions":[{"kind":"OperationDefinition","operation":"query","name":{"kind":"Name","value":"RouteAlternatives"},"variableDefinitions":[{"kind":"VariableDefinition","variable":{"kind":"Variable","name":{"kind":"Name","value":"origin"}},"type":{"kind":"NonNullType","type":{"kind":"NamedType","name":{"kind":"Name","value":"String"}}}},{"kind":"VariableDefinition","variable":{"kind":"Variable","name":{"kind":"Name","value":"destination"}},"type":{"kind":"NonNullType","type":{"kind":"NamedType","name":{"kind":"Name","value":"String"}}}}],"selectionSet":{"kind":"SelectionSet","selections":[{"kind":"Field","name":{"kind":"Name","value":"routeAlternatives"},"arguments":[{"kind":"Argument","name":{"kind":"Name","value":"origin"},"value":{"kind":"Variable","name":{"kind":"Name","value":"origin"}}},{"kind":"Argument","name":{"kind":"Name","value":"destination"},"value":{"kind":"Variable","name":{"kind":"Name","value":"destination"}}}],"selectionSet":{"kind":"SelectionSet","selections":[{"kind":"Field","name":{"kind":"Name","value":"fastestIndex"}},{"kind":"Field","name":{"kind":"Name","value":"smoothestIndex"}},{"kind":"Field","name":{"kind":"Name","value":"routes"},"selectionSet":{"kind":"SelectionSet","selections":[{"kind":"Field","name":{"kind":"Name","value":"index"}},{"kind":"Field","name":{"kind":"Name","value":"distanceM"}},{"kind":"Field","name":{"kind":"Name","value":"durationS"}},{"kind":"Field","name":{"kind":"Name","value":"summary"}},{"kind":"Field","name":{"kind":"Name","value":"coverage"}},{"kind":"Field","name":{"kind":"Name","value":"isFastest"}},{"kind":"Field","name":{"kind":"Name","value":"isSmoothest"}},{"kind":"Field","name":{"kind":"Name","value":"points"},"selectionSet":{"kind":"SelectionSet","selections":[{"kind":"Field","name":{"kind":"Name","value":"lat"}},{"kind":"Field","name":{"kind":"Name","value":"lng"}}]}},{"kind":"Field","name":{"kind":"Name","value":"quality"},"selectionSet":{"kind":"SelectionSet","selections":[{"kind":"Field","name":{"kind":"Name","value":"totalLengthM"}},{"kind":"Field","name":{"kind":"Name","value":"coveredLengthM"}},{"kind":"Field","name":{"kind":"Name","value":"lengthByRqi"}},{"kind":"Field","name":{"kind":"Name","value":"meanScore"}},{"kind":"Field","name":{"kind":"Name","value":"impactScore"}}]}}]}}]}}]}}]} as unknown as DocumentNode<RouteAlternativesQuery, RouteAlternativesQueryVariables>;
export const ProcessRouteDocument = {"kind":"Document","definitions":[{"kind":"OperationDefinition","operation":"mutation","name":{"kind":"Name","value":"ProcessRoute"},"variableDefinitions":[{"kind":"VariableDefinition","variable":{"kind":"Variable","name":{"kind":"Name","value":"input"}},"type":{"kind":"NonNullType","type":{"kind":"NamedType","name":{"kind":"Name","value":"ProcessRouteInput"}}}}],"selectionSet":{"kind":"SelectionSet","selections":[{"kind":"Field","name":{"kind":"Name","value":"processRoute"},"arguments":[{"kind":"Argument","name":{"kind":"Name","value":"input"},"value":{"kind":"Variable","name":{"kind":"Name","value":"input"}}}],"selectionSet":{"kind":"SelectionSet","selections":[{"kind":"Field","name":{"kind":"Name","value":"id"}},{"kind":"Field","name":{"kind":"Name","value":"status"}},{"kind":"Field","name":{"kind":"Name","value":"message"}}]}}]}}]} as unknown as DocumentNode<ProcessRouteMutation, ProcessRouteMutationVariables>;
export const GetActiveJobDocument = {"kind":"Document","definitions":[{"kind":"OperationDefinition","operation":"query","name":{"kind":"Name","value":"GetActiveJob"},"selectionSet":{"kind":"SelectionSet","selections":[{"kind":"Field","name":{"kind":"Name","value":"activeJob"},"selectionSet":{"kind":"SelectionSet","selections":[{"kind":"Field","name":{"kind":"Name","value":"id"}},{"kind":"Field","name":{"kind":"Name","value":"type"}},{"kind":"Field","name":{"kind":"Name","value":"status"}},{"kind":"Field","name":{"kind":"Name","value":"progress"}},{"kind":"Field","name":{"kind":"Name","value":"total"}},{"kind":"Field","name":{"kind":"Name","value":"details"}},{"kind":"Field","name":{"kind":"Name","value":"result"}}]}}]}}]} as unknown as DocumentNode<GetActiveJobQuery, GetActiveJobQueryVariables>;
export const GetRoadSegmentsDocument = {"kind":"Document","definitions":[{"kind":"OperationDefinition","operation":"query","name":{"kind":"Name","value":"GetRoadSegments"},"variableDefinitions":[{"kind":"VariableDefinition","variable":{"kind":"Variable","name":{"kind":"Name","value":"bbox"}},"type":{"kind":"NonNullType","type":{"kind":"ListType","type":{"kind":"NonNullType","type":{"kind":"NamedType","name":{"kind":"Name","value":"Float"}}}}}},{"kind":"VariableDefinition","variable":{"kind":"Variable","name":{"kind":"Name","value":"zoom"}},"type":{"kind":"NonNullType","type":{"kind":"NamedType","name":{"kind":"Name","value":"Int"}}}}],"selectionSet":{"kind":"SelectionSet","selections":[{"kind":"Field","name":{"kind":"Name","value":"roadSegments"},"arguments":[{"kind":"Argument","name":{"kind":"Name","value":"bbox"},"value":{"kind":"Variable","name":{"kind":"Name","value":"bbox"}}},{"kind":"Argument","name":{"kind":"Name","value":"zoom"},"value":{"kind":"Variable","name":{"kind":"Name","value":"zoom"}}}],"selectionSet":{"kind":"SelectionSet","selections":[{"kind":"Field","name":{"kind":"Name","value":"id"}},{"kind":"Field","name":{"kind":"Name","value":"path"}},{"kind":"Field","name":{"kind":"Name","value":"rqi"}},{"kind":"Field","name":{"kind":"Name","value":"score"}},{"kind":"Field","name":{"kind":"Name","value":"pBad"}},{"kind":"Field","name":{"kind":"Name","value":"confidence"}},{"kind":"Field","name":{"kind":"Name","value":"confidenceLevel"}},{"kind":"Field","name":{"kind":"Name","value":"confidenceReason"}},{"kind":"Field","name":{"kind":"Name","value":"nImages"}},{"kind":"Field","name":{"kind":"Name","value":"lengthM"}},{"kind":"Field","name":{"kind":"Name","value":"roadName"}},{"kind":"Field","name":{"kind":"Name","value":"highway"}},{"kind":"Field","name":{"kind":"Name","value":"captureDateMin"}},{"kind":"Field","name":{"kind":"Name","value":"captureDateMax"}}]}}]}}]} as unknown as DocumentNode<GetRoadSegmentsQuery, GetRoadSegmentsQueryVariables>;
export const GetRouteQualityDocument = {"kind":"Document","definitions":[{"kind":"OperationDefinition","operation":"query","name":{"kind":"Name","value":"GetRouteQuality"},"variableDefinitions":[{"kind":"VariableDefinition","variable":{"kind":"Variable","name":{"kind":"Name","value":"path"}},"type":{"kind":"NonNullType","type":{"kind":"ListType","type":{"kind":"NonNullType","type":{"kind":"ListType","type":{"kind":"NonNullType","type":{"kind":"NamedType","name":{"kind":"Name","value":"Float"}}}}}}}}],"selectionSet":{"kind":"SelectionSet","selections":[{"kind":"Field","name":{"kind":"Name","value":"routeQuality"},"arguments":[{"kind":"Argument","name":{"kind":"Name","value":"path"},"value":{"kind":"Variable","name":{"kind":"Name","value":"path"}}}],"selectionSet":{"kind":"SelectionSet","selections":[{"kind":"Field","name":{"kind":"Name","value":"totalLengthM"}},{"kind":"Field","name":{"kind":"Name","value":"coveredLengthM"}},{"kind":"Field","name":{"kind":"Name","value":"lengthByRqi"}},{"kind":"Field","name":{"kind":"Name","value":"meanScore"}},{"kind":"Field","name":{"kind":"Name","value":"worstSegments"},"selectionSet":{"kind":"SelectionSet","selections":[{"kind":"Field","name":{"kind":"Name","value":"id"}},{"kind":"Field","name":{"kind":"Name","value":"path"}},{"kind":"Field","name":{"kind":"Name","value":"rqi"}},{"kind":"Field","name":{"kind":"Name","value":"score"}},{"kind":"Field","name":{"kind":"Name","value":"pBad"}},{"kind":"Field","name":{"kind":"Name","value":"confidence"}},{"kind":"Field","name":{"kind":"Name","value":"confidenceLevel"}},{"kind":"Field","name":{"kind":"Name","value":"confidenceReason"}},{"kind":"Field","name":{"kind":"Name","value":"nImages"}},{"kind":"Field","name":{"kind":"Name","value":"lengthM"}},{"kind":"Field","name":{"kind":"Name","value":"roadName"}},{"kind":"Field","name":{"kind":"Name","value":"highway"}},{"kind":"Field","name":{"kind":"Name","value":"captureDateMin"}},{"kind":"Field","name":{"kind":"Name","value":"captureDateMax"}}]}}]}}]}}]} as unknown as DocumentNode<GetRouteQualityQuery, GetRouteQualityQueryVariables>;
export const GetSegmentFramesDocument = {"kind":"Document","definitions":[{"kind":"OperationDefinition","operation":"query","name":{"kind":"Name","value":"GetSegmentFrames"},"variableDefinitions":[{"kind":"VariableDefinition","variable":{"kind":"Variable","name":{"kind":"Name","value":"limit"}},"type":{"kind":"NamedType","name":{"kind":"Name","value":"Int"}}},{"kind":"VariableDefinition","variable":{"kind":"Variable","name":{"kind":"Name","value":"bbox"}},"type":{"kind":"ListType","type":{"kind":"NonNullType","type":{"kind":"NamedType","name":{"kind":"Name","value":"Float"}}}}}],"selectionSet":{"kind":"SelectionSet","selections":[{"kind":"Field","name":{"kind":"Name","value":"points"},"arguments":[{"kind":"Argument","name":{"kind":"Name","value":"limit"},"value":{"kind":"Variable","name":{"kind":"Name","value":"limit"}}},{"kind":"Argument","name":{"kind":"Name","value":"bbox"},"value":{"kind":"Variable","name":{"kind":"Name","value":"bbox"}}}],"selectionSet":{"kind":"SelectionSet","selections":[{"kind":"Field","name":{"kind":"Name","value":"id"}},{"kind":"Field","name":{"kind":"Name","value":"latitude"}},{"kind":"Field","name":{"kind":"Name","value":"longitude"}},{"kind":"Field","name":{"kind":"Name","value":"rqiScore"}},{"kind":"Field","name":{"kind":"Name","value":"rqiSource"}},{"kind":"Field","name":{"kind":"Name","value":"heading"}},{"kind":"Field","name":{"kind":"Name","value":"captureDate"}}]}}]}}]} as unknown as DocumentNode<GetSegmentFramesQuery, GetSegmentFramesQueryVariables>;
export const GetAvailableModelsDocument = {"kind":"Document","definitions":[{"kind":"OperationDefinition","operation":"query","name":{"kind":"Name","value":"GetAvailableModels"},"selectionSet":{"kind":"SelectionSet","selections":[{"kind":"Field","name":{"kind":"Name","value":"availableModels"}}]}}]} as unknown as DocumentNode<GetAvailableModelsQuery, GetAvailableModelsQueryVariables>;
export const GetSettingsDocument = {"kind":"Document","definitions":[{"kind":"OperationDefinition","operation":"query","name":{"kind":"Name","value":"GetSettings"},"selectionSet":{"kind":"SelectionSet","selections":[{"kind":"Field","name":{"kind":"Name","value":"settings"},"selectionSet":{"kind":"SelectionSet","selections":[{"kind":"Field","name":{"kind":"Name","value":"key"}},{"kind":"Field","name":{"kind":"Name","value":"value"}},{"kind":"Field","name":{"kind":"Name","value":"description"}},{"kind":"Field","name":{"kind":"Name","value":"example"}},{"kind":"Field","name":{"kind":"Name","value":"category"}},{"kind":"Field","name":{"kind":"Name","value":"explanation"}}]}}]}}]} as unknown as DocumentNode<GetSettingsQuery, GetSettingsQueryVariables>;
export const UpdateSettingDocument = {"kind":"Document","definitions":[{"kind":"OperationDefinition","operation":"mutation","name":{"kind":"Name","value":"UpdateSetting"},"variableDefinitions":[{"kind":"VariableDefinition","variable":{"kind":"Variable","name":{"kind":"Name","value":"input"}},"type":{"kind":"NonNullType","type":{"kind":"NamedType","name":{"kind":"Name","value":"UpdateSettingInput"}}}}],"selectionSet":{"kind":"SelectionSet","selections":[{"kind":"Field","name":{"kind":"Name","value":"updateSetting"},"arguments":[{"kind":"Argument","name":{"kind":"Name","value":"input"},"value":{"kind":"Variable","name":{"kind":"Name","value":"input"}}}],"selectionSet":{"kind":"SelectionSet","selections":[{"kind":"Field","name":{"kind":"Name","value":"key"}},{"kind":"Field","name":{"kind":"Name","value":"value"}},{"kind":"Field","name":{"kind":"Name","value":"description"}},{"kind":"Field","name":{"kind":"Name","value":"example"}},{"kind":"Field","name":{"kind":"Name","value":"category"}},{"kind":"Field","name":{"kind":"Name","value":"explanation"}}]}}]}}]} as unknown as DocumentNode<UpdateSettingMutation, UpdateSettingMutationVariables>;
export const GetRqiModelInfoDocument = {"kind":"Document","definitions":[{"kind":"OperationDefinition","operation":"query","name":{"kind":"Name","value":"GetRqiModelInfo"},"selectionSet":{"kind":"SelectionSet","selections":[{"kind":"Field","name":{"kind":"Name","value":"rqiModelInfo"},"selectionSet":{"kind":"SelectionSet","selections":[{"kind":"Field","name":{"kind":"Name","value":"available"}},{"kind":"Field","name":{"kind":"Name","value":"version"}},{"kind":"Field","name":{"kind":"Name","value":"backbone"}},{"kind":"Field","name":{"kind":"Name","value":"recipe"}},{"kind":"Field","name":{"kind":"Name","value":"head"}},{"kind":"Field","name":{"kind":"Name","value":"nTrain"}},{"kind":"Field","name":{"kind":"Name","value":"qwk"}},{"kind":"Field","name":{"kind":"Name","value":"mae"}},{"kind":"Field","name":{"kind":"Name","value":"exactAcc"}},{"kind":"Field","name":{"kind":"Name","value":"badRoadAcc"}},{"kind":"Field","name":{"kind":"Name","value":"badRoadAuc"}},{"kind":"Field","name":{"kind":"Name","value":"scaleMeaning"}},{"kind":"Field","name":{"kind":"Name","value":"metricsSource"}},{"kind":"Field","name":{"kind":"Name","value":"metricsProtocol"}},{"kind":"Field","name":{"kind":"Name","value":"metricsMeasuredOn"}},{"kind":"Field","name":{"kind":"Name","value":"segmentQwk"}},{"kind":"Field","name":{"kind":"Name","value":"segmentLengthM"}},{"kind":"Field","name":{"kind":"Name","value":"newAreaQwk"}}]}}]}}]} as unknown as DocumentNode<GetRqiModelInfoQuery, GetRqiModelInfoQueryVariables>;
export const GetTrainingDataDocument = {"kind":"Document","definitions":[{"kind":"OperationDefinition","operation":"query","name":{"kind":"Name","value":"GetTrainingData"},"variableDefinitions":[{"kind":"VariableDefinition","variable":{"kind":"Variable","name":{"kind":"Name","value":"id"}},"type":{"kind":"NonNullType","type":{"kind":"NamedType","name":{"kind":"Name","value":"Int"}}}}],"selectionSet":{"kind":"SelectionSet","selections":[{"kind":"Field","name":{"kind":"Name","value":"point"},"arguments":[{"kind":"Argument","name":{"kind":"Name","value":"id"},"value":{"kind":"Variable","name":{"kind":"Name","value":"id"}}}],"selectionSet":{"kind":"SelectionSet","selections":[{"kind":"Field","name":{"kind":"Name","value":"imageUrl"}},{"kind":"Field","name":{"kind":"Name","value":"manualRqi"}},{"kind":"Field","name":{"kind":"Name","value":"manualTags"}},{"kind":"Field","name":{"kind":"Name","value":"manualAnnotations"}},{"kind":"Field","name":{"kind":"Name","value":"manualComment"}}]}}]}}]} as unknown as DocumentNode<GetTrainingDataQuery, GetTrainingDataQueryVariables>;
export const SaveTrainingDataDocument = {"kind":"Document","definitions":[{"kind":"OperationDefinition","operation":"mutation","name":{"kind":"Name","value":"SaveTrainingData"},"variableDefinitions":[{"kind":"VariableDefinition","variable":{"kind":"Variable","name":{"kind":"Name","value":"input"}},"type":{"kind":"NonNullType","type":{"kind":"NamedType","name":{"kind":"Name","value":"TrainingDataInput"}}}}],"selectionSet":{"kind":"SelectionSet","selections":[{"kind":"Field","name":{"kind":"Name","value":"saveTrainingData"},"arguments":[{"kind":"Argument","name":{"kind":"Name","value":"input"},"value":{"kind":"Variable","name":{"kind":"Name","value":"input"}}}]}]}}]} as unknown as DocumentNode<SaveTrainingDataMutation, SaveTrainingDataMutationVariables>;
export const DeleteTrainingDataDocument = {"kind":"Document","definitions":[{"kind":"OperationDefinition","operation":"mutation","name":{"kind":"Name","value":"DeleteTrainingData"},"variableDefinitions":[{"kind":"VariableDefinition","variable":{"kind":"Variable","name":{"kind":"Name","value":"imageFilename"}},"type":{"kind":"NonNullType","type":{"kind":"NamedType","name":{"kind":"Name","value":"String"}}}}],"selectionSet":{"kind":"SelectionSet","selections":[{"kind":"Field","name":{"kind":"Name","value":"deleteTrainingData"},"arguments":[{"kind":"Argument","name":{"kind":"Name","value":"imageFilename"},"value":{"kind":"Variable","name":{"kind":"Name","value":"imageFilename"}}}]}]}}]} as unknown as DocumentNode<DeleteTrainingDataMutation, DeleteTrainingDataMutationVariables>;
export const GetTrainingPointsDocument = {"kind":"Document","definitions":[{"kind":"OperationDefinition","operation":"query","name":{"kind":"Name","value":"GetTrainingPoints"},"variableDefinitions":[{"kind":"VariableDefinition","variable":{"kind":"Variable","name":{"kind":"Name","value":"mode"}},"type":{"kind":"NamedType","name":{"kind":"Name","value":"FilterMode"}}},{"kind":"VariableDefinition","variable":{"kind":"Variable","name":{"kind":"Name","value":"limit"}},"type":{"kind":"NamedType","name":{"kind":"Name","value":"Int"}}},{"kind":"VariableDefinition","variable":{"kind":"Variable","name":{"kind":"Name","value":"offset"}},"type":{"kind":"NamedType","name":{"kind":"Name","value":"Int"}}},{"kind":"VariableDefinition","variable":{"kind":"Variable","name":{"kind":"Name","value":"model"}},"type":{"kind":"NamedType","name":{"kind":"Name","value":"String"}}}],"selectionSet":{"kind":"SelectionSet","selections":[{"kind":"Field","name":{"kind":"Name","value":"trainingPoints"},"arguments":[{"kind":"Argument","name":{"kind":"Name","value":"mode"},"value":{"kind":"Variable","name":{"kind":"Name","value":"mode"}}},{"kind":"Argument","name":{"kind":"Name","value":"limit"},"value":{"kind":"Variable","name":{"kind":"Name","value":"limit"}}},{"kind":"Argument","name":{"kind":"Name","value":"offset"},"value":{"kind":"Variable","name":{"kind":"Name","value":"offset"}}},{"kind":"Argument","name":{"kind":"Name","value":"model"},"value":{"kind":"Variable","name":{"kind":"Name","value":"model"}}}],"selectionSet":{"kind":"SelectionSet","selections":[{"kind":"Field","name":{"kind":"Name","value":"items"},"selectionSet":{"kind":"SelectionSet","selections":[{"kind":"Field","name":{"kind":"Name","value":"id"}},{"kind":"Field","name":{"kind":"Name","value":"latitude"}},{"kind":"Field","name":{"kind":"Name","value":"longitude"}},{"kind":"Field","name":{"kind":"Name","value":"imageUrl"}},{"kind":"Field","name":{"kind":"Name","value":"rqiScore"}},{"kind":"Field","name":{"kind":"Name","value":"dinoRqiScore"}},{"kind":"Field","name":{"kind":"Name","value":"manualRqi"}}]}},{"kind":"Field","name":{"kind":"Name","value":"totalCount"}},{"kind":"Field","name":{"kind":"Name","value":"hasMore"}}]}}]}}]} as unknown as DocumentNode<GetTrainingPointsQuery, GetTrainingPointsQueryVariables>;
export const GetTrainingStatsDocument = {"kind":"Document","definitions":[{"kind":"OperationDefinition","operation":"query","name":{"kind":"Name","value":"GetTrainingStats"},"variableDefinitions":[{"kind":"VariableDefinition","variable":{"kind":"Variable","name":{"kind":"Name","value":"mode"}},"type":{"kind":"NamedType","name":{"kind":"Name","value":"FilterMode"}}},{"kind":"VariableDefinition","variable":{"kind":"Variable","name":{"kind":"Name","value":"isDino"}},"type":{"kind":"NamedType","name":{"kind":"Name","value":"Boolean"}}}],"selectionSet":{"kind":"SelectionSet","selections":[{"kind":"Field","name":{"kind":"Name","value":"trainingStats"},"arguments":[{"kind":"Argument","name":{"kind":"Name","value":"mode"},"value":{"kind":"Variable","name":{"kind":"Name","value":"mode"}}},{"kind":"Argument","name":{"kind":"Name","value":"isDino"},"value":{"kind":"Variable","name":{"kind":"Name","value":"isDino"}}}],"selectionSet":{"kind":"SelectionSet","selections":[{"kind":"Field","name":{"kind":"Name","value":"total"}},{"kind":"Field","name":{"kind":"Name","value":"pending"}},{"kind":"Field","name":{"kind":"Name","value":"annotated"}},{"kind":"Field","name":{"kind":"Name","value":"avgRqi"}},{"kind":"Field","name":{"kind":"Name","value":"goodCount"}},{"kind":"Field","name":{"kind":"Name","value":"fairCount"}},{"kind":"Field","name":{"kind":"Name","value":"poorCount"}},{"kind":"Field","name":{"kind":"Name","value":"pendingAnalysis"}},{"kind":"Field","name":{"kind":"Name","value":"rqi1Count"}},{"kind":"Field","name":{"kind":"Name","value":"rqi2Count"}},{"kind":"Field","name":{"kind":"Name","value":"rqi3Count"}},{"kind":"Field","name":{"kind":"Name","value":"rqi4Count"}},{"kind":"Field","name":{"kind":"Name","value":"rqi5Count"}}]}}]}}]} as unknown as DocumentNode<GetTrainingStatsQuery, GetTrainingStatsQueryVariables>;
export const RunAnalysisDocument = {"kind":"Document","definitions":[{"kind":"OperationDefinition","operation":"mutation","name":{"kind":"Name","value":"RunAnalysis"},"variableDefinitions":[{"kind":"VariableDefinition","variable":{"kind":"Variable","name":{"kind":"Name","value":"input"}},"type":{"kind":"NonNullType","type":{"kind":"NamedType","name":{"kind":"Name","value":"RunAnalysisInput"}}}}],"selectionSet":{"kind":"SelectionSet","selections":[{"kind":"Field","name":{"kind":"Name","value":"runAnalysis"},"arguments":[{"kind":"Argument","name":{"kind":"Name","value":"input"},"value":{"kind":"Variable","name":{"kind":"Name","value":"input"}}}],"selectionSet":{"kind":"SelectionSet","selections":[{"kind":"Field","name":{"kind":"Name","value":"id"}}]}}]}}]} as unknown as DocumentNode<RunAnalysisMutation, RunAnalysisMutationVariables>;
export const StartModelTrainingDocument = {"kind":"Document","definitions":[{"kind":"OperationDefinition","operation":"mutation","name":{"kind":"Name","value":"StartModelTraining"},"selectionSet":{"kind":"SelectionSet","selections":[{"kind":"Field","name":{"kind":"Name","value":"startModelTraining"},"selectionSet":{"kind":"SelectionSet","selections":[{"kind":"Field","name":{"kind":"Name","value":"id"}}]}}]}}]} as unknown as DocumentNode<StartModelTrainingMutation, StartModelTrainingMutationVariables>;
export const StopJobDocument = {"kind":"Document","definitions":[{"kind":"OperationDefinition","operation":"mutation","name":{"kind":"Name","value":"StopJob"},"variableDefinitions":[{"kind":"VariableDefinition","variable":{"kind":"Variable","name":{"kind":"Name","value":"jobId"}},"type":{"kind":"NonNullType","type":{"kind":"NamedType","name":{"kind":"Name","value":"String"}}}}],"selectionSet":{"kind":"SelectionSet","selections":[{"kind":"Field","name":{"kind":"Name","value":"stopJob"},"arguments":[{"kind":"Argument","name":{"kind":"Name","value":"jobId"},"value":{"kind":"Variable","name":{"kind":"Name","value":"jobId"}}}]}]}}]} as unknown as DocumentNode<StopJobMutation, StopJobMutationVariables>;
export const PerformReviewActionDocument = {"kind":"Document","definitions":[{"kind":"OperationDefinition","operation":"mutation","name":{"kind":"Name","value":"PerformReviewAction"},"variableDefinitions":[{"kind":"VariableDefinition","variable":{"kind":"Variable","name":{"kind":"Name","value":"input"}},"type":{"kind":"NonNullType","type":{"kind":"NamedType","name":{"kind":"Name","value":"ReviewActionInput"}}}}],"selectionSet":{"kind":"SelectionSet","selections":[{"kind":"Field","name":{"kind":"Name","value":"performReviewAction"},"arguments":[{"kind":"Argument","name":{"kind":"Name","value":"input"},"value":{"kind":"Variable","name":{"kind":"Name","value":"input"}}}],"selectionSet":{"kind":"SelectionSet","selections":[{"kind":"Field","name":{"kind":"Name","value":"success"}},{"kind":"Field","name":{"kind":"Name","value":"message"}},{"kind":"Field","name":{"kind":"Name","value":"processedImageUrl"}},{"kind":"Field","name":{"kind":"Name","value":"annotations"},"selectionSet":{"kind":"SelectionSet","selections":[{"kind":"Field","name":{"kind":"Name","value":"id"}},{"kind":"Field","name":{"kind":"Name","value":"label"}},{"kind":"Field","name":{"kind":"Name","value":"score"}},{"kind":"Field","name":{"kind":"Name","value":"type"}},{"kind":"Field","name":{"kind":"Name","value":"points"}}]}}]}}]}}]} as unknown as DocumentNode<PerformReviewActionMutation, PerformReviewActionMutationVariables>;