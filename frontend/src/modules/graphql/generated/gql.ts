/* eslint-disable */
import * as types from './graphql';
import type { TypedDocumentNode as DocumentNode } from '@graphql-typed-document-node/core';

/**
 * Map of all GraphQL operations in the project.
 *
 * This map has several performance disadvantages:
 * 1. It is not tree-shakeable, so it will include all operations in the project.
 * 2. It is not minifiable, so the string of a GraphQL query will be multiple times inside the bundle.
 * 3. It does not support dead code elimination, so it will add unused operations.
 *
 * Therefore it is highly recommended to use the babel or swc plugin for production.
 * Learn more about it here: https://the-guild.dev/graphql/codegen/plugins/presets/preset-client#reducing-bundle-size
 */
type Documents = {
    "\n  query GetPoints($limit: Int, $bbox: [Float!]) {\n    points(limit: $limit, bbox: $bbox) {\n      id\n      latitude\n      longitude\n      rqiScore\n      heading\n    }\n  }\n": typeof types.GetPointsDocument,
    "\n  query GetPointDetail($id: Int!) {\n    point(id: $id) {\n      id\n      latitude\n      longitude\n      rqiScore\n      heading\n      pitch\n      imageUrl\n      # manual data\n      manualRqi\n      manualTags\n      manualAnnotations\n      # analysis\n      damageCount\n      damageTypes\n      analysisMetadata\n      createdAt\n    }\n  }\n": typeof types.GetPointDetailDocument,
    "\n  query GetRoute($origin: String!, $destination: String!) {\n    getRoute(origin: $origin, destination: $destination) {\n      points {\n        lat\n        lng\n      }\n    }\n  }\n": typeof types.GetRouteDocument,
    "\n  mutation ProcessRoute($input: ProcessRouteInput!) {\n    processRoute(input: $input) {\n      id\n      status\n      message\n    }\n  }\n": typeof types.ProcessRouteDocument,
    "\n  query GetAvailableModels {\n    availableModels\n  }\n": typeof types.GetAvailableModelsDocument,
    "\n  query GetSettings {\n    settings {\n      key\n      value\n      description\n      example\n      category\n      explanation\n    }\n  }\n": typeof types.GetSettingsDocument,
    "\n  mutation UpdateSetting($input: UpdateSettingInput!) {\n    updateSetting(input: $input) {\n      key\n      value\n      description\n      example\n      category\n      explanation\n    }\n  }\n": typeof types.UpdateSettingDocument,
    "\n  mutation ApplyPreset($values: JSON!) {\n    applyPreset(values: $values) {\n      key\n      value\n      description\n      example\n      category\n      explanation\n    }\n  }\n": typeof types.ApplyPresetDocument,
    "\n    query GetTrainingData($id: Int!) {\n        point(id: $id) {\n            imageUrl\n            manualRqi\n            manualTags\n            manualAnnotations\n            manualComment\n        }\n    }\n": typeof types.GetTrainingDataDocument,
    "\n    mutation SaveTrainingData($input: TrainingDataInput!) {\n        saveTrainingData(input: $input)\n    }\n": typeof types.SaveTrainingDataDocument,
    "\n    mutation DeleteTrainingData($imageFilename: String!) {\n        deleteTrainingData(imageFilename: $imageFilename)\n    }\n": typeof types.DeleteTrainingDataDocument,
    "\n  query GetTrainingPoints($mode: FilterMode, $limit: Int, $offset: Int) {\n    trainingPoints(mode: $mode, limit: $limit, offset: $offset) {\n      items {\n        id\n        latitude\n        longitude\n        imageUrl\n        rqiScore\n        manualRqi\n        manualTags\n        createdAt\n      }\n      totalCount\n      hasMore\n    }\n  }\n": typeof types.GetTrainingPointsDocument,
    "\n  query GetTrainingStats($mode: FilterMode) {\n    trainingStats(mode: $mode) {\n      total\n      pending\n      annotated\n      avgRqi\n      goodCount\n      fairCount\n      poorCount\n      pendingAnalysis\n    }\n  }\n": typeof types.GetTrainingStatsDocument,
    "\n    mutation RunAnalysis($input: RunAnalysisInput!) {\n        runAnalysis(input: $input) {\n            id\n        }\n    }\n": typeof types.RunAnalysisDocument,
    "\n    mutation StartModelTraining {\n        startModelTraining {\n            id\n        }\n    }\n": typeof types.StartModelTrainingDocument,
    "\n    mutation StopJob($jobId: String!) {\n        stopJob(jobId: $jobId)\n    }\n": typeof types.StopJobDocument,
    "\n    query GetActiveJob {\n        activeJob {\n            id\n            type\n            status\n            progress\n            total\n            details\n            result\n        }\n    }\n": typeof types.GetActiveJobDocument,
    "\n    query GetJob($id: String!) {\n        job(id: $id) {\n            id\n            type\n            status\n            progress\n            total\n            details\n            result\n            createdAt\n            completedAt\n        }\n    }\n": typeof types.GetJobDocument,
    "\n    mutation DetectObjects($input: DetectInput!) {\n        detectObjects(input: $input) {\n            label\n            confidence\n            points\n        }\n    }\n": typeof types.DetectObjectsDocument,
};
const documents: Documents = {
    "\n  query GetPoints($limit: Int, $bbox: [Float!]) {\n    points(limit: $limit, bbox: $bbox) {\n      id\n      latitude\n      longitude\n      rqiScore\n      heading\n    }\n  }\n": types.GetPointsDocument,
    "\n  query GetPointDetail($id: Int!) {\n    point(id: $id) {\n      id\n      latitude\n      longitude\n      rqiScore\n      heading\n      pitch\n      imageUrl\n      # manual data\n      manualRqi\n      manualTags\n      manualAnnotations\n      # analysis\n      damageCount\n      damageTypes\n      analysisMetadata\n      createdAt\n    }\n  }\n": types.GetPointDetailDocument,
    "\n  query GetRoute($origin: String!, $destination: String!) {\n    getRoute(origin: $origin, destination: $destination) {\n      points {\n        lat\n        lng\n      }\n    }\n  }\n": types.GetRouteDocument,
    "\n  mutation ProcessRoute($input: ProcessRouteInput!) {\n    processRoute(input: $input) {\n      id\n      status\n      message\n    }\n  }\n": types.ProcessRouteDocument,
    "\n  query GetAvailableModels {\n    availableModels\n  }\n": types.GetAvailableModelsDocument,
    "\n  query GetSettings {\n    settings {\n      key\n      value\n      description\n      example\n      category\n      explanation\n    }\n  }\n": types.GetSettingsDocument,
    "\n  mutation UpdateSetting($input: UpdateSettingInput!) {\n    updateSetting(input: $input) {\n      key\n      value\n      description\n      example\n      category\n      explanation\n    }\n  }\n": types.UpdateSettingDocument,
    "\n  mutation ApplyPreset($values: JSON!) {\n    applyPreset(values: $values) {\n      key\n      value\n      description\n      example\n      category\n      explanation\n    }\n  }\n": types.ApplyPresetDocument,
    "\n    query GetTrainingData($id: Int!) {\n        point(id: $id) {\n            imageUrl\n            manualRqi\n            manualTags\n            manualAnnotations\n            manualComment\n        }\n    }\n": types.GetTrainingDataDocument,
    "\n    mutation SaveTrainingData($input: TrainingDataInput!) {\n        saveTrainingData(input: $input)\n    }\n": types.SaveTrainingDataDocument,
    "\n    mutation DeleteTrainingData($imageFilename: String!) {\n        deleteTrainingData(imageFilename: $imageFilename)\n    }\n": types.DeleteTrainingDataDocument,
    "\n  query GetTrainingPoints($mode: FilterMode, $limit: Int, $offset: Int) {\n    trainingPoints(mode: $mode, limit: $limit, offset: $offset) {\n      items {\n        id\n        latitude\n        longitude\n        imageUrl\n        rqiScore\n        manualRqi\n        manualTags\n        createdAt\n      }\n      totalCount\n      hasMore\n    }\n  }\n": types.GetTrainingPointsDocument,
    "\n  query GetTrainingStats($mode: FilterMode) {\n    trainingStats(mode: $mode) {\n      total\n      pending\n      annotated\n      avgRqi\n      goodCount\n      fairCount\n      poorCount\n      pendingAnalysis\n    }\n  }\n": types.GetTrainingStatsDocument,
    "\n    mutation RunAnalysis($input: RunAnalysisInput!) {\n        runAnalysis(input: $input) {\n            id\n        }\n    }\n": types.RunAnalysisDocument,
    "\n    mutation StartModelTraining {\n        startModelTraining {\n            id\n        }\n    }\n": types.StartModelTrainingDocument,
    "\n    mutation StopJob($jobId: String!) {\n        stopJob(jobId: $jobId)\n    }\n": types.StopJobDocument,
    "\n    query GetActiveJob {\n        activeJob {\n            id\n            type\n            status\n            progress\n            total\n            details\n            result\n        }\n    }\n": types.GetActiveJobDocument,
    "\n    query GetJob($id: String!) {\n        job(id: $id) {\n            id\n            type\n            status\n            progress\n            total\n            details\n            result\n            createdAt\n            completedAt\n        }\n    }\n": types.GetJobDocument,
    "\n    mutation DetectObjects($input: DetectInput!) {\n        detectObjects(input: $input) {\n            label\n            confidence\n            points\n        }\n    }\n": types.DetectObjectsDocument,
};

/**
 * The gql function is used to parse GraphQL queries into a document that can be used by GraphQL clients.
 *
 *
 * @example
 * ```ts
 * const query = gql(`query GetUser($id: ID!) { user(id: $id) { name } }`);
 * ```
 *
 * The query argument is unknown!
 * Please regenerate the types.
 */
export function gql(source: string): unknown;

/**
 * The gql function is used to parse GraphQL queries into a document that can be used by GraphQL clients.
 */
export function gql(source: "\n  query GetPoints($limit: Int, $bbox: [Float!]) {\n    points(limit: $limit, bbox: $bbox) {\n      id\n      latitude\n      longitude\n      rqiScore\n      heading\n    }\n  }\n"): (typeof documents)["\n  query GetPoints($limit: Int, $bbox: [Float!]) {\n    points(limit: $limit, bbox: $bbox) {\n      id\n      latitude\n      longitude\n      rqiScore\n      heading\n    }\n  }\n"];
/**
 * The gql function is used to parse GraphQL queries into a document that can be used by GraphQL clients.
 */
export function gql(source: "\n  query GetPointDetail($id: Int!) {\n    point(id: $id) {\n      id\n      latitude\n      longitude\n      rqiScore\n      heading\n      pitch\n      imageUrl\n      # manual data\n      manualRqi\n      manualTags\n      manualAnnotations\n      # analysis\n      damageCount\n      damageTypes\n      analysisMetadata\n      createdAt\n    }\n  }\n"): (typeof documents)["\n  query GetPointDetail($id: Int!) {\n    point(id: $id) {\n      id\n      latitude\n      longitude\n      rqiScore\n      heading\n      pitch\n      imageUrl\n      # manual data\n      manualRqi\n      manualTags\n      manualAnnotations\n      # analysis\n      damageCount\n      damageTypes\n      analysisMetadata\n      createdAt\n    }\n  }\n"];
/**
 * The gql function is used to parse GraphQL queries into a document that can be used by GraphQL clients.
 */
export function gql(source: "\n  query GetRoute($origin: String!, $destination: String!) {\n    getRoute(origin: $origin, destination: $destination) {\n      points {\n        lat\n        lng\n      }\n    }\n  }\n"): (typeof documents)["\n  query GetRoute($origin: String!, $destination: String!) {\n    getRoute(origin: $origin, destination: $destination) {\n      points {\n        lat\n        lng\n      }\n    }\n  }\n"];
/**
 * The gql function is used to parse GraphQL queries into a document that can be used by GraphQL clients.
 */
export function gql(source: "\n  mutation ProcessRoute($input: ProcessRouteInput!) {\n    processRoute(input: $input) {\n      id\n      status\n      message\n    }\n  }\n"): (typeof documents)["\n  mutation ProcessRoute($input: ProcessRouteInput!) {\n    processRoute(input: $input) {\n      id\n      status\n      message\n    }\n  }\n"];
/**
 * The gql function is used to parse GraphQL queries into a document that can be used by GraphQL clients.
 */
export function gql(source: "\n  query GetAvailableModels {\n    availableModels\n  }\n"): (typeof documents)["\n  query GetAvailableModels {\n    availableModels\n  }\n"];
/**
 * The gql function is used to parse GraphQL queries into a document that can be used by GraphQL clients.
 */
export function gql(source: "\n  query GetSettings {\n    settings {\n      key\n      value\n      description\n      example\n      category\n      explanation\n    }\n  }\n"): (typeof documents)["\n  query GetSettings {\n    settings {\n      key\n      value\n      description\n      example\n      category\n      explanation\n    }\n  }\n"];
/**
 * The gql function is used to parse GraphQL queries into a document that can be used by GraphQL clients.
 */
export function gql(source: "\n  mutation UpdateSetting($input: UpdateSettingInput!) {\n    updateSetting(input: $input) {\n      key\n      value\n      description\n      example\n      category\n      explanation\n    }\n  }\n"): (typeof documents)["\n  mutation UpdateSetting($input: UpdateSettingInput!) {\n    updateSetting(input: $input) {\n      key\n      value\n      description\n      example\n      category\n      explanation\n    }\n  }\n"];
/**
 * The gql function is used to parse GraphQL queries into a document that can be used by GraphQL clients.
 */
export function gql(source: "\n  mutation ApplyPreset($values: JSON!) {\n    applyPreset(values: $values) {\n      key\n      value\n      description\n      example\n      category\n      explanation\n    }\n  }\n"): (typeof documents)["\n  mutation ApplyPreset($values: JSON!) {\n    applyPreset(values: $values) {\n      key\n      value\n      description\n      example\n      category\n      explanation\n    }\n  }\n"];
/**
 * The gql function is used to parse GraphQL queries into a document that can be used by GraphQL clients.
 */
export function gql(source: "\n    query GetTrainingData($id: Int!) {\n        point(id: $id) {\n            imageUrl\n            manualRqi\n            manualTags\n            manualAnnotations\n            manualComment\n        }\n    }\n"): (typeof documents)["\n    query GetTrainingData($id: Int!) {\n        point(id: $id) {\n            imageUrl\n            manualRqi\n            manualTags\n            manualAnnotations\n            manualComment\n        }\n    }\n"];
/**
 * The gql function is used to parse GraphQL queries into a document that can be used by GraphQL clients.
 */
export function gql(source: "\n    mutation SaveTrainingData($input: TrainingDataInput!) {\n        saveTrainingData(input: $input)\n    }\n"): (typeof documents)["\n    mutation SaveTrainingData($input: TrainingDataInput!) {\n        saveTrainingData(input: $input)\n    }\n"];
/**
 * The gql function is used to parse GraphQL queries into a document that can be used by GraphQL clients.
 */
export function gql(source: "\n    mutation DeleteTrainingData($imageFilename: String!) {\n        deleteTrainingData(imageFilename: $imageFilename)\n    }\n"): (typeof documents)["\n    mutation DeleteTrainingData($imageFilename: String!) {\n        deleteTrainingData(imageFilename: $imageFilename)\n    }\n"];
/**
 * The gql function is used to parse GraphQL queries into a document that can be used by GraphQL clients.
 */
export function gql(source: "\n  query GetTrainingPoints($mode: FilterMode, $limit: Int, $offset: Int) {\n    trainingPoints(mode: $mode, limit: $limit, offset: $offset) {\n      items {\n        id\n        latitude\n        longitude\n        imageUrl\n        rqiScore\n        manualRqi\n        manualTags\n        createdAt\n      }\n      totalCount\n      hasMore\n    }\n  }\n"): (typeof documents)["\n  query GetTrainingPoints($mode: FilterMode, $limit: Int, $offset: Int) {\n    trainingPoints(mode: $mode, limit: $limit, offset: $offset) {\n      items {\n        id\n        latitude\n        longitude\n        imageUrl\n        rqiScore\n        manualRqi\n        manualTags\n        createdAt\n      }\n      totalCount\n      hasMore\n    }\n  }\n"];
/**
 * The gql function is used to parse GraphQL queries into a document that can be used by GraphQL clients.
 */
export function gql(source: "\n  query GetTrainingStats($mode: FilterMode) {\n    trainingStats(mode: $mode) {\n      total\n      pending\n      annotated\n      avgRqi\n      goodCount\n      fairCount\n      poorCount\n      pendingAnalysis\n    }\n  }\n"): (typeof documents)["\n  query GetTrainingStats($mode: FilterMode) {\n    trainingStats(mode: $mode) {\n      total\n      pending\n      annotated\n      avgRqi\n      goodCount\n      fairCount\n      poorCount\n      pendingAnalysis\n    }\n  }\n"];
/**
 * The gql function is used to parse GraphQL queries into a document that can be used by GraphQL clients.
 */
export function gql(source: "\n    mutation RunAnalysis($input: RunAnalysisInput!) {\n        runAnalysis(input: $input) {\n            id\n        }\n    }\n"): (typeof documents)["\n    mutation RunAnalysis($input: RunAnalysisInput!) {\n        runAnalysis(input: $input) {\n            id\n        }\n    }\n"];
/**
 * The gql function is used to parse GraphQL queries into a document that can be used by GraphQL clients.
 */
export function gql(source: "\n    mutation StartModelTraining {\n        startModelTraining {\n            id\n        }\n    }\n"): (typeof documents)["\n    mutation StartModelTraining {\n        startModelTraining {\n            id\n        }\n    }\n"];
/**
 * The gql function is used to parse GraphQL queries into a document that can be used by GraphQL clients.
 */
export function gql(source: "\n    mutation StopJob($jobId: String!) {\n        stopJob(jobId: $jobId)\n    }\n"): (typeof documents)["\n    mutation StopJob($jobId: String!) {\n        stopJob(jobId: $jobId)\n    }\n"];
/**
 * The gql function is used to parse GraphQL queries into a document that can be used by GraphQL clients.
 */
export function gql(source: "\n    query GetActiveJob {\n        activeJob {\n            id\n            type\n            status\n            progress\n            total\n            details\n            result\n        }\n    }\n"): (typeof documents)["\n    query GetActiveJob {\n        activeJob {\n            id\n            type\n            status\n            progress\n            total\n            details\n            result\n        }\n    }\n"];
/**
 * The gql function is used to parse GraphQL queries into a document that can be used by GraphQL clients.
 */
export function gql(source: "\n    query GetJob($id: String!) {\n        job(id: $id) {\n            id\n            type\n            status\n            progress\n            total\n            details\n            result\n            createdAt\n            completedAt\n        }\n    }\n"): (typeof documents)["\n    query GetJob($id: String!) {\n        job(id: $id) {\n            id\n            type\n            status\n            progress\n            total\n            details\n            result\n            createdAt\n            completedAt\n        }\n    }\n"];
/**
 * The gql function is used to parse GraphQL queries into a document that can be used by GraphQL clients.
 */
export function gql(source: "\n    mutation DetectObjects($input: DetectInput!) {\n        detectObjects(input: $input) {\n            label\n            confidence\n            points\n        }\n    }\n"): (typeof documents)["\n    mutation DetectObjects($input: DetectInput!) {\n        detectObjects(input: $input) {\n            label\n            confidence\n            points\n        }\n    }\n"];

export function gql(source: string) {
  return (documents as any)[source] ?? {};
}

export type DocumentType<TDocumentNode extends DocumentNode<any, any>> = TDocumentNode extends DocumentNode<  infer TType,  any>  ? TType  : never;