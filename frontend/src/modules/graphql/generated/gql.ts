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
    "\n    query GetTrainingData($id: Int!) {\n        point(id: $id) {\n            imageUrl\n            manualRqi\n            manualTags\n            manualAnnotations\n            manualComment\n        }\n    }\n": typeof types.GetTrainingDataDocument,
    "\n    mutation SaveTrainingData($input: TrainingDataInput!) {\n        saveTrainingData(input: $input)\n    }\n": typeof types.SaveTrainingDataDocument,
    "\n  query GetTrainingPoints($mode: FilterMode, $limit: Int, $offset: Int) {\n    trainingPoints(mode: $mode, limit: $limit, offset: $offset) {\n      items {\n        id\n        latitude\n        longitude\n        imageUrl\n        rqiScore\n        manualRqi\n        manualTags\n        createdAt\n      }\n      totalCount\n      hasMore\n    }\n  }\n": typeof types.GetTrainingPointsDocument,
    "\n  query GetTrainingStats($mode: FilterMode) {\n    trainingStats(mode: $mode) {\n      total\n      pending\n      annotated\n      avgRqi\n      goodCount\n      fairCount\n      poorCount\n    }\n  }\n": typeof types.GetTrainingStatsDocument,
    "\n    mutation RunAnalysis($input: RunAnalysisInput!) {\n        runAnalysis(input: $input) {\n            jobId\n        }\n    }\n": typeof types.RunAnalysisDocument,
    "\n    mutation StartModelTraining {\n        startModelTraining {\n            jobId\n        }\n    }\n": typeof types.StartModelTrainingDocument,
    "\n    query GetJobStatus($id: String!) {\n        job(id: $id) {\n            jobId\n            status\n            progress\n            total\n            message\n            error\n        }\n    }\n": typeof types.GetJobStatusDocument,
};
const documents: Documents = {
    "\n  query GetPoints($limit: Int, $bbox: [Float!]) {\n    points(limit: $limit, bbox: $bbox) {\n      id\n      latitude\n      longitude\n      rqiScore\n      heading\n    }\n  }\n": types.GetPointsDocument,
    "\n  query GetPointDetail($id: Int!) {\n    point(id: $id) {\n      id\n      latitude\n      longitude\n      rqiScore\n      heading\n      pitch\n      imageUrl\n      # manual data\n      manualRqi\n      manualTags\n      manualAnnotations\n      # analysis\n      damageCount\n      damageTypes\n      analysisMetadata\n      createdAt\n    }\n  }\n": types.GetPointDetailDocument,
    "\n    query GetTrainingData($id: Int!) {\n        point(id: $id) {\n            imageUrl\n            manualRqi\n            manualTags\n            manualAnnotations\n            manualComment\n        }\n    }\n": types.GetTrainingDataDocument,
    "\n    mutation SaveTrainingData($input: TrainingDataInput!) {\n        saveTrainingData(input: $input)\n    }\n": types.SaveTrainingDataDocument,
    "\n  query GetTrainingPoints($mode: FilterMode, $limit: Int, $offset: Int) {\n    trainingPoints(mode: $mode, limit: $limit, offset: $offset) {\n      items {\n        id\n        latitude\n        longitude\n        imageUrl\n        rqiScore\n        manualRqi\n        manualTags\n        createdAt\n      }\n      totalCount\n      hasMore\n    }\n  }\n": types.GetTrainingPointsDocument,
    "\n  query GetTrainingStats($mode: FilterMode) {\n    trainingStats(mode: $mode) {\n      total\n      pending\n      annotated\n      avgRqi\n      goodCount\n      fairCount\n      poorCount\n    }\n  }\n": types.GetTrainingStatsDocument,
    "\n    mutation RunAnalysis($input: RunAnalysisInput!) {\n        runAnalysis(input: $input) {\n            jobId\n        }\n    }\n": types.RunAnalysisDocument,
    "\n    mutation StartModelTraining {\n        startModelTraining {\n            jobId\n        }\n    }\n": types.StartModelTrainingDocument,
    "\n    query GetJobStatus($id: String!) {\n        job(id: $id) {\n            jobId\n            status\n            progress\n            total\n            message\n            error\n        }\n    }\n": types.GetJobStatusDocument,
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
export function gql(source: "\n    query GetTrainingData($id: Int!) {\n        point(id: $id) {\n            imageUrl\n            manualRqi\n            manualTags\n            manualAnnotations\n            manualComment\n        }\n    }\n"): (typeof documents)["\n    query GetTrainingData($id: Int!) {\n        point(id: $id) {\n            imageUrl\n            manualRqi\n            manualTags\n            manualAnnotations\n            manualComment\n        }\n    }\n"];
/**
 * The gql function is used to parse GraphQL queries into a document that can be used by GraphQL clients.
 */
export function gql(source: "\n    mutation SaveTrainingData($input: TrainingDataInput!) {\n        saveTrainingData(input: $input)\n    }\n"): (typeof documents)["\n    mutation SaveTrainingData($input: TrainingDataInput!) {\n        saveTrainingData(input: $input)\n    }\n"];
/**
 * The gql function is used to parse GraphQL queries into a document that can be used by GraphQL clients.
 */
export function gql(source: "\n  query GetTrainingPoints($mode: FilterMode, $limit: Int, $offset: Int) {\n    trainingPoints(mode: $mode, limit: $limit, offset: $offset) {\n      items {\n        id\n        latitude\n        longitude\n        imageUrl\n        rqiScore\n        manualRqi\n        manualTags\n        createdAt\n      }\n      totalCount\n      hasMore\n    }\n  }\n"): (typeof documents)["\n  query GetTrainingPoints($mode: FilterMode, $limit: Int, $offset: Int) {\n    trainingPoints(mode: $mode, limit: $limit, offset: $offset) {\n      items {\n        id\n        latitude\n        longitude\n        imageUrl\n        rqiScore\n        manualRqi\n        manualTags\n        createdAt\n      }\n      totalCount\n      hasMore\n    }\n  }\n"];
/**
 * The gql function is used to parse GraphQL queries into a document that can be used by GraphQL clients.
 */
export function gql(source: "\n  query GetTrainingStats($mode: FilterMode) {\n    trainingStats(mode: $mode) {\n      total\n      pending\n      annotated\n      avgRqi\n      goodCount\n      fairCount\n      poorCount\n    }\n  }\n"): (typeof documents)["\n  query GetTrainingStats($mode: FilterMode) {\n    trainingStats(mode: $mode) {\n      total\n      pending\n      annotated\n      avgRqi\n      goodCount\n      fairCount\n      poorCount\n    }\n  }\n"];
/**
 * The gql function is used to parse GraphQL queries into a document that can be used by GraphQL clients.
 */
export function gql(source: "\n    mutation RunAnalysis($input: RunAnalysisInput!) {\n        runAnalysis(input: $input) {\n            jobId\n        }\n    }\n"): (typeof documents)["\n    mutation RunAnalysis($input: RunAnalysisInput!) {\n        runAnalysis(input: $input) {\n            jobId\n        }\n    }\n"];
/**
 * The gql function is used to parse GraphQL queries into a document that can be used by GraphQL clients.
 */
export function gql(source: "\n    mutation StartModelTraining {\n        startModelTraining {\n            jobId\n        }\n    }\n"): (typeof documents)["\n    mutation StartModelTraining {\n        startModelTraining {\n            jobId\n        }\n    }\n"];
/**
 * The gql function is used to parse GraphQL queries into a document that can be used by GraphQL clients.
 */
export function gql(source: "\n    query GetJobStatus($id: String!) {\n        job(id: $id) {\n            jobId\n            status\n            progress\n            total\n            message\n            error\n        }\n    }\n"): (typeof documents)["\n    query GetJobStatus($id: String!) {\n        job(id: $id) {\n            jobId\n            status\n            progress\n            total\n            message\n            error\n        }\n    }\n"];

export function gql(source: string) {
  return (documents as any)[source] ?? {};
}

export type DocumentType<TDocumentNode extends DocumentNode<any, any>> = TDocumentNode extends DocumentNode<  infer TType,  any>  ? TType  : never;