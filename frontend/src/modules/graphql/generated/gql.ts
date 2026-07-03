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
    "\n  query GetJob($id: String!) {\n    job(id: $id) {\n      id\n      status\n      progress\n      total\n      message\n      result\n      error\n      createdAt\n      completedAt\n    }\n  }\n": typeof types.GetJobDocument,
    "\n  query Viewer {\n    me {\n      clerkId\n      email\n      role\n    }\n  }\n": typeof types.ViewerDocument,
    "\n  query GetPoints($limit: Int, $bbox: [Float!]) {\n    points(limit: $limit, bbox: $bbox) {\n      id\n      latitude\n      longitude\n      rqiScore\n      dinoRqiScore\n      rqiSource\n      heading\n    }\n  }\n": typeof types.GetPointsDocument,
    "\n  query GetRoadQualityGrid($zoom: Int!, $bbox: [Float!]) {\n    roadQualityGrid(zoom: $zoom, bbox: $bbox)\n  }\n": typeof types.GetRoadQualityGridDocument,
    "\n  query GetPointDetail($id: Int!) {\n    point(id: $id) {\n      id\n      latitude\n      longitude\n      rqiScore\n      dinoRqiScore\n      dinoScore\n      dinoPBad\n      rqiSource\n      heading\n      pitch\n      imageUrl\n      # manual data\n      manualRqi\n      manualTags\n      manualAnnotations\n# ...\n      # analysis\n      damageCount\n      damageTypes\n      analysisMetadata\n      createdAt\n    }\n  }\n": typeof types.GetPointDetailDocument,
    "\n  query GetRoute($origin: String!, $destination: String!) {\n    getRoute(origin: $origin, destination: $destination) {\n      points {\n        lat\n        lng\n      }\n    }\n  }\n": typeof types.GetRouteDocument,
    "\n  mutation ProcessRoute($input: ProcessRouteInput!) {\n    processRoute(input: $input) {\n      id\n      status\n      message\n    }\n  }\n": typeof types.ProcessRouteDocument,
    "\n    query GetActiveJob {\n        activeJob {\n            id\n            type\n            status\n            progress\n            total\n            details\n            result\n        }\n    }\n": typeof types.GetActiveJobDocument,
    "\n  query GetAvailableModels {\n    availableModels\n  }\n": typeof types.GetAvailableModelsDocument,
    "\n  query GetSettings {\n    settings {\n      key\n      value\n      description\n      example\n      category\n      explanation\n    }\n  }\n": typeof types.GetSettingsDocument,
    "\n  mutation UpdateSetting($input: UpdateSettingInput!) {\n    updateSetting(input: $input) {\n      key\n      value\n      description\n      example\n      category\n      explanation\n    }\n  }\n": typeof types.UpdateSettingDocument,
    "\n  query GetRqiModelInfo {\n    rqiModelInfo {\n      available\n      version\n      backbone\n      recipe\n      head\n      nTrain\n      qwk\n      mae\n      exactAcc\n      badRoadAcc\n      badRoadAuc\n      scaleMeaning\n    }\n  }\n": typeof types.GetRqiModelInfoDocument,
    "\n    query GetTrainingData($id: Int!) {\n        point(id: $id) {\n            imageUrl\n            manualRqi\n            manualTags\n            manualAnnotations\n            manualComment\n        }\n    }\n": typeof types.GetTrainingDataDocument,
    "\n    mutation SaveTrainingData($input: TrainingDataInput!) {\n        saveTrainingData(input: $input)\n    }\n": typeof types.SaveTrainingDataDocument,
    "\n    mutation DeleteTrainingData($imageFilename: String!) {\n        deleteTrainingData(imageFilename: $imageFilename)\n    }\n": typeof types.DeleteTrainingDataDocument,
    "\n  query GetTrainingPoints($mode: FilterMode, $limit: Int, $offset: Int, $model: String) {\n    trainingPoints(mode: $mode, limit: $limit, offset: $offset, model: $model) {\n      items {\n        id\n        latitude\n        longitude\n        imageUrl\n        rqiScore\n        dinoRqiScore\n        manualRqi\n      }\n      totalCount\n      hasMore\n    }\n  }\n": typeof types.GetTrainingPointsDocument,
    "\n  query GetTrainingStats($mode: FilterMode, $isDino: Boolean) {\n    trainingStats(mode: $mode, isDino: $isDino) {\n      total\n      pending\n      annotated\n      avgRqi\n      goodCount\n      fairCount\n      poorCount\n      pendingAnalysis\n      rqi1Count\n      rqi2Count\n      rqi3Count\n      rqi4Count\n      rqi5Count\n    }\n  }\n": typeof types.GetTrainingStatsDocument,
    "\n    mutation RunAnalysis($input: RunAnalysisInput!) {\n        runAnalysis(input: $input) {\n            id\n        }\n    }\n": typeof types.RunAnalysisDocument,
    "\n    mutation StartModelTraining {\n        startModelTraining {\n            id\n        }\n    }\n": typeof types.StartModelTrainingDocument,
    "\n    mutation StopJob($jobId: String!) {\n        stopJob(jobId: $jobId)\n    }\n": typeof types.StopJobDocument,
    "\n    mutation PerformReviewAction($input: ReviewActionInput!) {\n        performReviewAction(input: $input) {\n            success\n            message\n            processedImageUrl\n            annotations {\n                id\n                label\n                score\n                type\n                points\n            }\n        }\n    }\n": typeof types.PerformReviewActionDocument,
};
const documents: Documents = {
    "\n  query GetJob($id: String!) {\n    job(id: $id) {\n      id\n      status\n      progress\n      total\n      message\n      result\n      error\n      createdAt\n      completedAt\n    }\n  }\n": types.GetJobDocument,
    "\n  query Viewer {\n    me {\n      clerkId\n      email\n      role\n    }\n  }\n": types.ViewerDocument,
    "\n  query GetPoints($limit: Int, $bbox: [Float!]) {\n    points(limit: $limit, bbox: $bbox) {\n      id\n      latitude\n      longitude\n      rqiScore\n      dinoRqiScore\n      rqiSource\n      heading\n    }\n  }\n": types.GetPointsDocument,
    "\n  query GetRoadQualityGrid($zoom: Int!, $bbox: [Float!]) {\n    roadQualityGrid(zoom: $zoom, bbox: $bbox)\n  }\n": types.GetRoadQualityGridDocument,
    "\n  query GetPointDetail($id: Int!) {\n    point(id: $id) {\n      id\n      latitude\n      longitude\n      rqiScore\n      dinoRqiScore\n      dinoScore\n      dinoPBad\n      rqiSource\n      heading\n      pitch\n      imageUrl\n      # manual data\n      manualRqi\n      manualTags\n      manualAnnotations\n# ...\n      # analysis\n      damageCount\n      damageTypes\n      analysisMetadata\n      createdAt\n    }\n  }\n": types.GetPointDetailDocument,
    "\n  query GetRoute($origin: String!, $destination: String!) {\n    getRoute(origin: $origin, destination: $destination) {\n      points {\n        lat\n        lng\n      }\n    }\n  }\n": types.GetRouteDocument,
    "\n  mutation ProcessRoute($input: ProcessRouteInput!) {\n    processRoute(input: $input) {\n      id\n      status\n      message\n    }\n  }\n": types.ProcessRouteDocument,
    "\n    query GetActiveJob {\n        activeJob {\n            id\n            type\n            status\n            progress\n            total\n            details\n            result\n        }\n    }\n": types.GetActiveJobDocument,
    "\n  query GetAvailableModels {\n    availableModels\n  }\n": types.GetAvailableModelsDocument,
    "\n  query GetSettings {\n    settings {\n      key\n      value\n      description\n      example\n      category\n      explanation\n    }\n  }\n": types.GetSettingsDocument,
    "\n  mutation UpdateSetting($input: UpdateSettingInput!) {\n    updateSetting(input: $input) {\n      key\n      value\n      description\n      example\n      category\n      explanation\n    }\n  }\n": types.UpdateSettingDocument,
    "\n  query GetRqiModelInfo {\n    rqiModelInfo {\n      available\n      version\n      backbone\n      recipe\n      head\n      nTrain\n      qwk\n      mae\n      exactAcc\n      badRoadAcc\n      badRoadAuc\n      scaleMeaning\n    }\n  }\n": types.GetRqiModelInfoDocument,
    "\n    query GetTrainingData($id: Int!) {\n        point(id: $id) {\n            imageUrl\n            manualRqi\n            manualTags\n            manualAnnotations\n            manualComment\n        }\n    }\n": types.GetTrainingDataDocument,
    "\n    mutation SaveTrainingData($input: TrainingDataInput!) {\n        saveTrainingData(input: $input)\n    }\n": types.SaveTrainingDataDocument,
    "\n    mutation DeleteTrainingData($imageFilename: String!) {\n        deleteTrainingData(imageFilename: $imageFilename)\n    }\n": types.DeleteTrainingDataDocument,
    "\n  query GetTrainingPoints($mode: FilterMode, $limit: Int, $offset: Int, $model: String) {\n    trainingPoints(mode: $mode, limit: $limit, offset: $offset, model: $model) {\n      items {\n        id\n        latitude\n        longitude\n        imageUrl\n        rqiScore\n        dinoRqiScore\n        manualRqi\n      }\n      totalCount\n      hasMore\n    }\n  }\n": types.GetTrainingPointsDocument,
    "\n  query GetTrainingStats($mode: FilterMode, $isDino: Boolean) {\n    trainingStats(mode: $mode, isDino: $isDino) {\n      total\n      pending\n      annotated\n      avgRqi\n      goodCount\n      fairCount\n      poorCount\n      pendingAnalysis\n      rqi1Count\n      rqi2Count\n      rqi3Count\n      rqi4Count\n      rqi5Count\n    }\n  }\n": types.GetTrainingStatsDocument,
    "\n    mutation RunAnalysis($input: RunAnalysisInput!) {\n        runAnalysis(input: $input) {\n            id\n        }\n    }\n": types.RunAnalysisDocument,
    "\n    mutation StartModelTraining {\n        startModelTraining {\n            id\n        }\n    }\n": types.StartModelTrainingDocument,
    "\n    mutation StopJob($jobId: String!) {\n        stopJob(jobId: $jobId)\n    }\n": types.StopJobDocument,
    "\n    mutation PerformReviewAction($input: ReviewActionInput!) {\n        performReviewAction(input: $input) {\n            success\n            message\n            processedImageUrl\n            annotations {\n                id\n                label\n                score\n                type\n                points\n            }\n        }\n    }\n": types.PerformReviewActionDocument,
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
export function gql(source: "\n  query GetJob($id: String!) {\n    job(id: $id) {\n      id\n      status\n      progress\n      total\n      message\n      result\n      error\n      createdAt\n      completedAt\n    }\n  }\n"): (typeof documents)["\n  query GetJob($id: String!) {\n    job(id: $id) {\n      id\n      status\n      progress\n      total\n      message\n      result\n      error\n      createdAt\n      completedAt\n    }\n  }\n"];
/**
 * The gql function is used to parse GraphQL queries into a document that can be used by GraphQL clients.
 */
export function gql(source: "\n  query Viewer {\n    me {\n      clerkId\n      email\n      role\n    }\n  }\n"): (typeof documents)["\n  query Viewer {\n    me {\n      clerkId\n      email\n      role\n    }\n  }\n"];
/**
 * The gql function is used to parse GraphQL queries into a document that can be used by GraphQL clients.
 */
export function gql(source: "\n  query GetPoints($limit: Int, $bbox: [Float!]) {\n    points(limit: $limit, bbox: $bbox) {\n      id\n      latitude\n      longitude\n      rqiScore\n      dinoRqiScore\n      rqiSource\n      heading\n    }\n  }\n"): (typeof documents)["\n  query GetPoints($limit: Int, $bbox: [Float!]) {\n    points(limit: $limit, bbox: $bbox) {\n      id\n      latitude\n      longitude\n      rqiScore\n      dinoRqiScore\n      rqiSource\n      heading\n    }\n  }\n"];
/**
 * The gql function is used to parse GraphQL queries into a document that can be used by GraphQL clients.
 */
export function gql(source: "\n  query GetRoadQualityGrid($zoom: Int!, $bbox: [Float!]) {\n    roadQualityGrid(zoom: $zoom, bbox: $bbox)\n  }\n"): (typeof documents)["\n  query GetRoadQualityGrid($zoom: Int!, $bbox: [Float!]) {\n    roadQualityGrid(zoom: $zoom, bbox: $bbox)\n  }\n"];
/**
 * The gql function is used to parse GraphQL queries into a document that can be used by GraphQL clients.
 */
export function gql(source: "\n  query GetPointDetail($id: Int!) {\n    point(id: $id) {\n      id\n      latitude\n      longitude\n      rqiScore\n      dinoRqiScore\n      dinoScore\n      dinoPBad\n      rqiSource\n      heading\n      pitch\n      imageUrl\n      # manual data\n      manualRqi\n      manualTags\n      manualAnnotations\n# ...\n      # analysis\n      damageCount\n      damageTypes\n      analysisMetadata\n      createdAt\n    }\n  }\n"): (typeof documents)["\n  query GetPointDetail($id: Int!) {\n    point(id: $id) {\n      id\n      latitude\n      longitude\n      rqiScore\n      dinoRqiScore\n      dinoScore\n      dinoPBad\n      rqiSource\n      heading\n      pitch\n      imageUrl\n      # manual data\n      manualRqi\n      manualTags\n      manualAnnotations\n# ...\n      # analysis\n      damageCount\n      damageTypes\n      analysisMetadata\n      createdAt\n    }\n  }\n"];
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
export function gql(source: "\n    query GetActiveJob {\n        activeJob {\n            id\n            type\n            status\n            progress\n            total\n            details\n            result\n        }\n    }\n"): (typeof documents)["\n    query GetActiveJob {\n        activeJob {\n            id\n            type\n            status\n            progress\n            total\n            details\n            result\n        }\n    }\n"];
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
export function gql(source: "\n  query GetRqiModelInfo {\n    rqiModelInfo {\n      available\n      version\n      backbone\n      recipe\n      head\n      nTrain\n      qwk\n      mae\n      exactAcc\n      badRoadAcc\n      badRoadAuc\n      scaleMeaning\n    }\n  }\n"): (typeof documents)["\n  query GetRqiModelInfo {\n    rqiModelInfo {\n      available\n      version\n      backbone\n      recipe\n      head\n      nTrain\n      qwk\n      mae\n      exactAcc\n      badRoadAcc\n      badRoadAuc\n      scaleMeaning\n    }\n  }\n"];
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
export function gql(source: "\n  query GetTrainingPoints($mode: FilterMode, $limit: Int, $offset: Int, $model: String) {\n    trainingPoints(mode: $mode, limit: $limit, offset: $offset, model: $model) {\n      items {\n        id\n        latitude\n        longitude\n        imageUrl\n        rqiScore\n        dinoRqiScore\n        manualRqi\n      }\n      totalCount\n      hasMore\n    }\n  }\n"): (typeof documents)["\n  query GetTrainingPoints($mode: FilterMode, $limit: Int, $offset: Int, $model: String) {\n    trainingPoints(mode: $mode, limit: $limit, offset: $offset, model: $model) {\n      items {\n        id\n        latitude\n        longitude\n        imageUrl\n        rqiScore\n        dinoRqiScore\n        manualRqi\n      }\n      totalCount\n      hasMore\n    }\n  }\n"];
/**
 * The gql function is used to parse GraphQL queries into a document that can be used by GraphQL clients.
 */
export function gql(source: "\n  query GetTrainingStats($mode: FilterMode, $isDino: Boolean) {\n    trainingStats(mode: $mode, isDino: $isDino) {\n      total\n      pending\n      annotated\n      avgRqi\n      goodCount\n      fairCount\n      poorCount\n      pendingAnalysis\n      rqi1Count\n      rqi2Count\n      rqi3Count\n      rqi4Count\n      rqi5Count\n    }\n  }\n"): (typeof documents)["\n  query GetTrainingStats($mode: FilterMode, $isDino: Boolean) {\n    trainingStats(mode: $mode, isDino: $isDino) {\n      total\n      pending\n      annotated\n      avgRqi\n      goodCount\n      fairCount\n      poorCount\n      pendingAnalysis\n      rqi1Count\n      rqi2Count\n      rqi3Count\n      rqi4Count\n      rqi5Count\n    }\n  }\n"];
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
export function gql(source: "\n    mutation PerformReviewAction($input: ReviewActionInput!) {\n        performReviewAction(input: $input) {\n            success\n            message\n            processedImageUrl\n            annotations {\n                id\n                label\n                score\n                type\n                points\n            }\n        }\n    }\n"): (typeof documents)["\n    mutation PerformReviewAction($input: ReviewActionInput!) {\n        performReviewAction(input: $input) {\n            success\n            message\n            processedImageUrl\n            annotations {\n                id\n                label\n                score\n                type\n                points\n            }\n        }\n    }\n"];

export function gql(source: string) {
  return (documents as any)[source] ?? {};
}

export type DocumentType<TDocumentNode extends DocumentNode<any, any>> = TDocumentNode extends DocumentNode<  infer TType,  any>  ? TType  : never;