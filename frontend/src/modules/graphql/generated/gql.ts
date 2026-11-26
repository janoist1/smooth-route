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
    "\n  query AdminStats {\n    adminStats {\n      totalImages\n      imagesThisMonth\n      freeTierLimit\n      billableThisMonth\n      totalPoints\n      analyzedPoints\n      pendingAnalysis\n      rqiGood\n      rqiFair\n      rqiPoor\n      totalUsers\n      adminUsers\n      imagesPerDay {\n        day\n        count\n      }\n      recentJobs {\n        id\n        status\n        message\n        progress\n        total\n      }\n    }\n  }\n": typeof types.AdminStatsDocument,
    "\n  query ModelAdmin {\n    modelAdmin {\n      trainedOn\n      newLabels\n      newByArea {\n        area\n        count\n      }\n      newByLevel {\n        level\n        count\n      }\n      sprintLabelled\n      sprintTarget\n      hint\n      candidateAvailable\n      report\n      reportVerdict\n      reportGatePass\n      reportAt\n      confirmPhrase\n    }\n  }\n": typeof types.ModelAdminDocument,
    "\n  mutation StartRetrain {\n    startRetrain\n  }\n": typeof types.StartRetrainDocument,
    "\n  mutation PromoteCandidate($confirm: String!) {\n    promoteCandidate(confirm: $confirm)\n  }\n": typeof types.PromoteCandidateDocument,
    "\n  mutation StartRescoreAndRebuild {\n    startRescoreAndRebuild\n  }\n": typeof types.StartRescoreAndRebuildDocument,
    "\n  query GetJob($id: String!) {\n    job(id: $id) {\n      id\n      status\n      progress\n      total\n      message\n      result\n      error\n      createdAt\n      completedAt\n    }\n  }\n": typeof types.GetJobDocument,
    "\n  query Viewer {\n    me {\n      clerkId\n      email\n      role\n    }\n  }\n": typeof types.ViewerDocument,
    "\n  query LabelQueue($strategy: LabelQueueStrategy!, $limit: Int!, $excludeIds: [Int!]) {\n    labelQueue(strategy: $strategy, limit: $limit, excludeIds: $excludeIds) {\n      strategy\n      items {\n        id\n        imageUrl\n        latitude\n        longitude\n        heading\n        captureDate\n        streetViewUrl\n        reason\n        area\n        uncertainty\n        cellLabels\n        boundary\n        modelScore\n        modelRqi\n        modelPBad\n      }\n      stats {\n        totalLabelled\n        labelledToday\n        eligible\n        scored\n        rechecked\n        recheckSame\n        recheckWithinOne\n        sprintLabelled\n        sprintTarget\n      }\n    }\n  }\n": typeof types.LabelQueueDocument,
    "\n  query PairQueue($limit: Int!, $excludeIds: [Int!]) {\n    pairQueue(limit: $limit, excludeIds: $excludeIds) {\n      judged\n      pairs {\n        scoreGap\n        a {\n        id\n        imageUrl\n        latitude\n        longitude\n        heading\n        captureDate\n        streetViewUrl\n        reason\n        area\n        uncertainty\n        cellLabels\n        boundary\n        modelScore\n        modelRqi\n        modelPBad\n        }\n        b {\n        id\n        imageUrl\n        latitude\n        longitude\n        heading\n        captureDate\n        streetViewUrl\n        reason\n        area\n        uncertainty\n        cellLabels\n        boundary\n        modelScore\n        modelRqi\n        modelPBad\n        }\n      }\n    }\n  }\n": typeof types.PairQueueDocument,
    "\n  mutation SubmitPairJudgment($input: PairJudgmentInput!) {\n    submitPairJudgment(input: $input)\n  }\n": typeof types.SubmitPairJudgmentDocument,
    "\n  mutation UndoPairJudgment($clientId: String!) {\n    undoPairJudgment(clientId: $clientId)\n  }\n": typeof types.UndoPairJudgmentDocument,
    "\n  query LabelExamples($perClass: Int!) {\n    labelExamples(perClass: $perClass) {\n      rqi\n      id\n      imageUrl\n    }\n  }\n": typeof types.LabelExamplesDocument,
    "\n  mutation QuickLabel($input: QuickLabelInput!) {\n    quickLabel(input: $input) {\n      pointId\n      rqi\n      totalLabelled\n      labelledToday\n    }\n  }\n": typeof types.QuickLabelDocument,
    "\n  mutation UndoQuickLabel($pointId: Int!) {\n    undoQuickLabel(pointId: $pointId)\n  }\n": typeof types.UndoQuickLabelDocument,
    "\n  query GetPoints($limit: Int, $bbox: [Float!]) {\n    points(limit: $limit, bbox: $bbox) {\n      id\n      latitude\n      longitude\n      rqiScore\n      dinoRqiScore\n      rqiSource\n      heading\n      captureDate\n    }\n  }\n": typeof types.GetPointsDocument,
    "\n  query GetRoadQualityGrid($zoom: Int!, $bbox: [Float!]) {\n    roadQualityGrid(zoom: $zoom, bbox: $bbox)\n  }\n": typeof types.GetRoadQualityGridDocument,
    "\n  query GetPointDetail($id: Int!) {\n    point(id: $id) {\n      id\n      latitude\n      longitude\n      rqiScore\n      dinoRqiScore\n      dinoScore\n      dinoPBad\n      rqiSource\n      heading\n      pitch\n      imageUrl\n      streetViewUrl\n      captureDate\n      # manual data\n      manualRqi\n      manualTags\n      manualAnnotations\n# ...\n      # analysis\n      damageCount\n      damageTypes\n      analysisMetadata\n      createdAt\n    }\n  }\n": typeof types.GetPointDetailDocument,
    "\n  query RouteAlternatives($origin: String!, $destination: String!) {\n    routeAlternatives(origin: $origin, destination: $destination) {\n      fastestIndex\n      smoothestIndex\n      routes {\n        index\n        distanceM\n        durationS\n        summary\n        coverage\n        isFastest\n        isSmoothest\n        points {\n          lat\n          lng\n        }\n        quality {\n          totalLengthM\n          coveredLengthM\n          lengthByRqi\n          meanScore\n          meanRqi\n          impactScore\n        }\n      }\n    }\n  }\n": typeof types.RouteAlternativesDocument,
    "\n  mutation ProcessRoute($input: ProcessRouteInput!) {\n    processRoute(input: $input) {\n      id\n      status\n      message\n    }\n  }\n": typeof types.ProcessRouteDocument,
    "\n    query GetActiveJob {\n        activeJob {\n            id\n            type\n            status\n            progress\n            total\n            details\n            result\n        }\n    }\n": typeof types.GetActiveJobDocument,
    "\n  query GetRoadSegments($bbox: [Float!]!, $zoom: Int!) {\n    roadSegments(bbox: $bbox, zoom: $zoom) {\n      id\n      path\n      rqi\n      score\n      pBad\n      confidence\n      confidenceLevel\n      confidenceReason\n      nImages\n      lengthM\n      roadName\n      highway\n      captureDateMin\n      captureDateMax\n    }\n  }\n": typeof types.GetRoadSegmentsDocument,
    "\n  query GetRouteQuality($path: [[Float!]!]!) {\n    routeQuality(path: $path) {\n      totalLengthM\n      coveredLengthM\n      lengthByRqi\n      meanScore\n      impactScore\n      meanRqi\n      worstSegments {\n        id\n        path\n        rqi\n        score\n        pBad\n        confidence\n        confidenceLevel\n        confidenceReason\n        nImages\n        lengthM\n        roadName\n        highway\n        captureDateMin\n        captureDateMax\n      }\n    }\n  }\n": typeof types.GetRouteQualityDocument,
    "\n  query GetSegmentFrames($segmentId: ID!) {\n    segmentFrames(segmentId: $segmentId) {\n      id\n      latitude\n      longitude\n      rqiScore\n      rqiSource\n      heading\n      captureDate\n    }\n  }\n": typeof types.GetSegmentFramesDocument,
    "\n  query GetAvailableModels {\n    availableModels\n  }\n": typeof types.GetAvailableModelsDocument,
    "\n  query GetSettings {\n    settings {\n      key\n      value\n      description\n      example\n      category\n      explanation\n    }\n  }\n": typeof types.GetSettingsDocument,
    "\n  mutation UpdateSetting($input: UpdateSettingInput!) {\n    updateSetting(input: $input) {\n      key\n      value\n      description\n      example\n      category\n      explanation\n    }\n  }\n": typeof types.UpdateSettingDocument,
    "\n  query GetRqiModelInfo {\n    rqiModelInfo {\n      available\n      version\n      backbone\n      recipe\n      head\n      nTrain\n      qwk\n      mae\n      exactAcc\n      badRoadAcc\n      badRoadAuc\n      scaleMeaning\n      metricsSource\n      metricsProtocol\n      metricsMeasuredOn\n      segmentQwk\n      segmentLengthM\n      newAreaQwk\n    }\n  }\n": typeof types.GetRqiModelInfoDocument,
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
    "\n  query AdminStats {\n    adminStats {\n      totalImages\n      imagesThisMonth\n      freeTierLimit\n      billableThisMonth\n      totalPoints\n      analyzedPoints\n      pendingAnalysis\n      rqiGood\n      rqiFair\n      rqiPoor\n      totalUsers\n      adminUsers\n      imagesPerDay {\n        day\n        count\n      }\n      recentJobs {\n        id\n        status\n        message\n        progress\n        total\n      }\n    }\n  }\n": types.AdminStatsDocument,
    "\n  query ModelAdmin {\n    modelAdmin {\n      trainedOn\n      newLabels\n      newByArea {\n        area\n        count\n      }\n      newByLevel {\n        level\n        count\n      }\n      sprintLabelled\n      sprintTarget\n      hint\n      candidateAvailable\n      report\n      reportVerdict\n      reportGatePass\n      reportAt\n      confirmPhrase\n    }\n  }\n": types.ModelAdminDocument,
    "\n  mutation StartRetrain {\n    startRetrain\n  }\n": types.StartRetrainDocument,
    "\n  mutation PromoteCandidate($confirm: String!) {\n    promoteCandidate(confirm: $confirm)\n  }\n": types.PromoteCandidateDocument,
    "\n  mutation StartRescoreAndRebuild {\n    startRescoreAndRebuild\n  }\n": types.StartRescoreAndRebuildDocument,
    "\n  query GetJob($id: String!) {\n    job(id: $id) {\n      id\n      status\n      progress\n      total\n      message\n      result\n      error\n      createdAt\n      completedAt\n    }\n  }\n": types.GetJobDocument,
    "\n  query Viewer {\n    me {\n      clerkId\n      email\n      role\n    }\n  }\n": types.ViewerDocument,
    "\n  query LabelQueue($strategy: LabelQueueStrategy!, $limit: Int!, $excludeIds: [Int!]) {\n    labelQueue(strategy: $strategy, limit: $limit, excludeIds: $excludeIds) {\n      strategy\n      items {\n        id\n        imageUrl\n        latitude\n        longitude\n        heading\n        captureDate\n        streetViewUrl\n        reason\n        area\n        uncertainty\n        cellLabels\n        boundary\n        modelScore\n        modelRqi\n        modelPBad\n      }\n      stats {\n        totalLabelled\n        labelledToday\n        eligible\n        scored\n        rechecked\n        recheckSame\n        recheckWithinOne\n        sprintLabelled\n        sprintTarget\n      }\n    }\n  }\n": types.LabelQueueDocument,
    "\n  query PairQueue($limit: Int!, $excludeIds: [Int!]) {\n    pairQueue(limit: $limit, excludeIds: $excludeIds) {\n      judged\n      pairs {\n        scoreGap\n        a {\n        id\n        imageUrl\n        latitude\n        longitude\n        heading\n        captureDate\n        streetViewUrl\n        reason\n        area\n        uncertainty\n        cellLabels\n        boundary\n        modelScore\n        modelRqi\n        modelPBad\n        }\n        b {\n        id\n        imageUrl\n        latitude\n        longitude\n        heading\n        captureDate\n        streetViewUrl\n        reason\n        area\n        uncertainty\n        cellLabels\n        boundary\n        modelScore\n        modelRqi\n        modelPBad\n        }\n      }\n    }\n  }\n": types.PairQueueDocument,
    "\n  mutation SubmitPairJudgment($input: PairJudgmentInput!) {\n    submitPairJudgment(input: $input)\n  }\n": types.SubmitPairJudgmentDocument,
    "\n  mutation UndoPairJudgment($clientId: String!) {\n    undoPairJudgment(clientId: $clientId)\n  }\n": types.UndoPairJudgmentDocument,
    "\n  query LabelExamples($perClass: Int!) {\n    labelExamples(perClass: $perClass) {\n      rqi\n      id\n      imageUrl\n    }\n  }\n": types.LabelExamplesDocument,
    "\n  mutation QuickLabel($input: QuickLabelInput!) {\n    quickLabel(input: $input) {\n      pointId\n      rqi\n      totalLabelled\n      labelledToday\n    }\n  }\n": types.QuickLabelDocument,
    "\n  mutation UndoQuickLabel($pointId: Int!) {\n    undoQuickLabel(pointId: $pointId)\n  }\n": types.UndoQuickLabelDocument,
    "\n  query GetPoints($limit: Int, $bbox: [Float!]) {\n    points(limit: $limit, bbox: $bbox) {\n      id\n      latitude\n      longitude\n      rqiScore\n      dinoRqiScore\n      rqiSource\n      heading\n      captureDate\n    }\n  }\n": types.GetPointsDocument,
    "\n  query GetRoadQualityGrid($zoom: Int!, $bbox: [Float!]) {\n    roadQualityGrid(zoom: $zoom, bbox: $bbox)\n  }\n": types.GetRoadQualityGridDocument,
    "\n  query GetPointDetail($id: Int!) {\n    point(id: $id) {\n      id\n      latitude\n      longitude\n      rqiScore\n      dinoRqiScore\n      dinoScore\n      dinoPBad\n      rqiSource\n      heading\n      pitch\n      imageUrl\n      streetViewUrl\n      captureDate\n      # manual data\n      manualRqi\n      manualTags\n      manualAnnotations\n# ...\n      # analysis\n      damageCount\n      damageTypes\n      analysisMetadata\n      createdAt\n    }\n  }\n": types.GetPointDetailDocument,
    "\n  query RouteAlternatives($origin: String!, $destination: String!) {\n    routeAlternatives(origin: $origin, destination: $destination) {\n      fastestIndex\n      smoothestIndex\n      routes {\n        index\n        distanceM\n        durationS\n        summary\n        coverage\n        isFastest\n        isSmoothest\n        points {\n          lat\n          lng\n        }\n        quality {\n          totalLengthM\n          coveredLengthM\n          lengthByRqi\n          meanScore\n          meanRqi\n          impactScore\n        }\n      }\n    }\n  }\n": types.RouteAlternativesDocument,
    "\n  mutation ProcessRoute($input: ProcessRouteInput!) {\n    processRoute(input: $input) {\n      id\n      status\n      message\n    }\n  }\n": types.ProcessRouteDocument,
    "\n    query GetActiveJob {\n        activeJob {\n            id\n            type\n            status\n            progress\n            total\n            details\n            result\n        }\n    }\n": types.GetActiveJobDocument,
    "\n  query GetRoadSegments($bbox: [Float!]!, $zoom: Int!) {\n    roadSegments(bbox: $bbox, zoom: $zoom) {\n      id\n      path\n      rqi\n      score\n      pBad\n      confidence\n      confidenceLevel\n      confidenceReason\n      nImages\n      lengthM\n      roadName\n      highway\n      captureDateMin\n      captureDateMax\n    }\n  }\n": types.GetRoadSegmentsDocument,
    "\n  query GetRouteQuality($path: [[Float!]!]!) {\n    routeQuality(path: $path) {\n      totalLengthM\n      coveredLengthM\n      lengthByRqi\n      meanScore\n      impactScore\n      meanRqi\n      worstSegments {\n        id\n        path\n        rqi\n        score\n        pBad\n        confidence\n        confidenceLevel\n        confidenceReason\n        nImages\n        lengthM\n        roadName\n        highway\n        captureDateMin\n        captureDateMax\n      }\n    }\n  }\n": types.GetRouteQualityDocument,
    "\n  query GetSegmentFrames($segmentId: ID!) {\n    segmentFrames(segmentId: $segmentId) {\n      id\n      latitude\n      longitude\n      rqiScore\n      rqiSource\n      heading\n      captureDate\n    }\n  }\n": types.GetSegmentFramesDocument,
    "\n  query GetAvailableModels {\n    availableModels\n  }\n": types.GetAvailableModelsDocument,
    "\n  query GetSettings {\n    settings {\n      key\n      value\n      description\n      example\n      category\n      explanation\n    }\n  }\n": types.GetSettingsDocument,
    "\n  mutation UpdateSetting($input: UpdateSettingInput!) {\n    updateSetting(input: $input) {\n      key\n      value\n      description\n      example\n      category\n      explanation\n    }\n  }\n": types.UpdateSettingDocument,
    "\n  query GetRqiModelInfo {\n    rqiModelInfo {\n      available\n      version\n      backbone\n      recipe\n      head\n      nTrain\n      qwk\n      mae\n      exactAcc\n      badRoadAcc\n      badRoadAuc\n      scaleMeaning\n      metricsSource\n      metricsProtocol\n      metricsMeasuredOn\n      segmentQwk\n      segmentLengthM\n      newAreaQwk\n    }\n  }\n": types.GetRqiModelInfoDocument,
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
export function gql(source: "\n  query AdminStats {\n    adminStats {\n      totalImages\n      imagesThisMonth\n      freeTierLimit\n      billableThisMonth\n      totalPoints\n      analyzedPoints\n      pendingAnalysis\n      rqiGood\n      rqiFair\n      rqiPoor\n      totalUsers\n      adminUsers\n      imagesPerDay {\n        day\n        count\n      }\n      recentJobs {\n        id\n        status\n        message\n        progress\n        total\n      }\n    }\n  }\n"): (typeof documents)["\n  query AdminStats {\n    adminStats {\n      totalImages\n      imagesThisMonth\n      freeTierLimit\n      billableThisMonth\n      totalPoints\n      analyzedPoints\n      pendingAnalysis\n      rqiGood\n      rqiFair\n      rqiPoor\n      totalUsers\n      adminUsers\n      imagesPerDay {\n        day\n        count\n      }\n      recentJobs {\n        id\n        status\n        message\n        progress\n        total\n      }\n    }\n  }\n"];
/**
 * The gql function is used to parse GraphQL queries into a document that can be used by GraphQL clients.
 */
export function gql(source: "\n  query ModelAdmin {\n    modelAdmin {\n      trainedOn\n      newLabels\n      newByArea {\n        area\n        count\n      }\n      newByLevel {\n        level\n        count\n      }\n      sprintLabelled\n      sprintTarget\n      hint\n      candidateAvailable\n      report\n      reportVerdict\n      reportGatePass\n      reportAt\n      confirmPhrase\n    }\n  }\n"): (typeof documents)["\n  query ModelAdmin {\n    modelAdmin {\n      trainedOn\n      newLabels\n      newByArea {\n        area\n        count\n      }\n      newByLevel {\n        level\n        count\n      }\n      sprintLabelled\n      sprintTarget\n      hint\n      candidateAvailable\n      report\n      reportVerdict\n      reportGatePass\n      reportAt\n      confirmPhrase\n    }\n  }\n"];
/**
 * The gql function is used to parse GraphQL queries into a document that can be used by GraphQL clients.
 */
export function gql(source: "\n  mutation StartRetrain {\n    startRetrain\n  }\n"): (typeof documents)["\n  mutation StartRetrain {\n    startRetrain\n  }\n"];
/**
 * The gql function is used to parse GraphQL queries into a document that can be used by GraphQL clients.
 */
export function gql(source: "\n  mutation PromoteCandidate($confirm: String!) {\n    promoteCandidate(confirm: $confirm)\n  }\n"): (typeof documents)["\n  mutation PromoteCandidate($confirm: String!) {\n    promoteCandidate(confirm: $confirm)\n  }\n"];
/**
 * The gql function is used to parse GraphQL queries into a document that can be used by GraphQL clients.
 */
export function gql(source: "\n  mutation StartRescoreAndRebuild {\n    startRescoreAndRebuild\n  }\n"): (typeof documents)["\n  mutation StartRescoreAndRebuild {\n    startRescoreAndRebuild\n  }\n"];
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
export function gql(source: "\n  query LabelQueue($strategy: LabelQueueStrategy!, $limit: Int!, $excludeIds: [Int!]) {\n    labelQueue(strategy: $strategy, limit: $limit, excludeIds: $excludeIds) {\n      strategy\n      items {\n        id\n        imageUrl\n        latitude\n        longitude\n        heading\n        captureDate\n        streetViewUrl\n        reason\n        area\n        uncertainty\n        cellLabels\n        boundary\n        modelScore\n        modelRqi\n        modelPBad\n      }\n      stats {\n        totalLabelled\n        labelledToday\n        eligible\n        scored\n        rechecked\n        recheckSame\n        recheckWithinOne\n        sprintLabelled\n        sprintTarget\n      }\n    }\n  }\n"): (typeof documents)["\n  query LabelQueue($strategy: LabelQueueStrategy!, $limit: Int!, $excludeIds: [Int!]) {\n    labelQueue(strategy: $strategy, limit: $limit, excludeIds: $excludeIds) {\n      strategy\n      items {\n        id\n        imageUrl\n        latitude\n        longitude\n        heading\n        captureDate\n        streetViewUrl\n        reason\n        area\n        uncertainty\n        cellLabels\n        boundary\n        modelScore\n        modelRqi\n        modelPBad\n      }\n      stats {\n        totalLabelled\n        labelledToday\n        eligible\n        scored\n        rechecked\n        recheckSame\n        recheckWithinOne\n        sprintLabelled\n        sprintTarget\n      }\n    }\n  }\n"];
/**
 * The gql function is used to parse GraphQL queries into a document that can be used by GraphQL clients.
 */
export function gql(source: "\n  query PairQueue($limit: Int!, $excludeIds: [Int!]) {\n    pairQueue(limit: $limit, excludeIds: $excludeIds) {\n      judged\n      pairs {\n        scoreGap\n        a {\n        id\n        imageUrl\n        latitude\n        longitude\n        heading\n        captureDate\n        streetViewUrl\n        reason\n        area\n        uncertainty\n        cellLabels\n        boundary\n        modelScore\n        modelRqi\n        modelPBad\n        }\n        b {\n        id\n        imageUrl\n        latitude\n        longitude\n        heading\n        captureDate\n        streetViewUrl\n        reason\n        area\n        uncertainty\n        cellLabels\n        boundary\n        modelScore\n        modelRqi\n        modelPBad\n        }\n      }\n    }\n  }\n"): (typeof documents)["\n  query PairQueue($limit: Int!, $excludeIds: [Int!]) {\n    pairQueue(limit: $limit, excludeIds: $excludeIds) {\n      judged\n      pairs {\n        scoreGap\n        a {\n        id\n        imageUrl\n        latitude\n        longitude\n        heading\n        captureDate\n        streetViewUrl\n        reason\n        area\n        uncertainty\n        cellLabels\n        boundary\n        modelScore\n        modelRqi\n        modelPBad\n        }\n        b {\n        id\n        imageUrl\n        latitude\n        longitude\n        heading\n        captureDate\n        streetViewUrl\n        reason\n        area\n        uncertainty\n        cellLabels\n        boundary\n        modelScore\n        modelRqi\n        modelPBad\n        }\n      }\n    }\n  }\n"];
/**
 * The gql function is used to parse GraphQL queries into a document that can be used by GraphQL clients.
 */
export function gql(source: "\n  mutation SubmitPairJudgment($input: PairJudgmentInput!) {\n    submitPairJudgment(input: $input)\n  }\n"): (typeof documents)["\n  mutation SubmitPairJudgment($input: PairJudgmentInput!) {\n    submitPairJudgment(input: $input)\n  }\n"];
/**
 * The gql function is used to parse GraphQL queries into a document that can be used by GraphQL clients.
 */
export function gql(source: "\n  mutation UndoPairJudgment($clientId: String!) {\n    undoPairJudgment(clientId: $clientId)\n  }\n"): (typeof documents)["\n  mutation UndoPairJudgment($clientId: String!) {\n    undoPairJudgment(clientId: $clientId)\n  }\n"];
/**
 * The gql function is used to parse GraphQL queries into a document that can be used by GraphQL clients.
 */
export function gql(source: "\n  query LabelExamples($perClass: Int!) {\n    labelExamples(perClass: $perClass) {\n      rqi\n      id\n      imageUrl\n    }\n  }\n"): (typeof documents)["\n  query LabelExamples($perClass: Int!) {\n    labelExamples(perClass: $perClass) {\n      rqi\n      id\n      imageUrl\n    }\n  }\n"];
/**
 * The gql function is used to parse GraphQL queries into a document that can be used by GraphQL clients.
 */
export function gql(source: "\n  mutation QuickLabel($input: QuickLabelInput!) {\n    quickLabel(input: $input) {\n      pointId\n      rqi\n      totalLabelled\n      labelledToday\n    }\n  }\n"): (typeof documents)["\n  mutation QuickLabel($input: QuickLabelInput!) {\n    quickLabel(input: $input) {\n      pointId\n      rqi\n      totalLabelled\n      labelledToday\n    }\n  }\n"];
/**
 * The gql function is used to parse GraphQL queries into a document that can be used by GraphQL clients.
 */
export function gql(source: "\n  mutation UndoQuickLabel($pointId: Int!) {\n    undoQuickLabel(pointId: $pointId)\n  }\n"): (typeof documents)["\n  mutation UndoQuickLabel($pointId: Int!) {\n    undoQuickLabel(pointId: $pointId)\n  }\n"];
/**
 * The gql function is used to parse GraphQL queries into a document that can be used by GraphQL clients.
 */
export function gql(source: "\n  query GetPoints($limit: Int, $bbox: [Float!]) {\n    points(limit: $limit, bbox: $bbox) {\n      id\n      latitude\n      longitude\n      rqiScore\n      dinoRqiScore\n      rqiSource\n      heading\n      captureDate\n    }\n  }\n"): (typeof documents)["\n  query GetPoints($limit: Int, $bbox: [Float!]) {\n    points(limit: $limit, bbox: $bbox) {\n      id\n      latitude\n      longitude\n      rqiScore\n      dinoRqiScore\n      rqiSource\n      heading\n      captureDate\n    }\n  }\n"];
/**
 * The gql function is used to parse GraphQL queries into a document that can be used by GraphQL clients.
 */
export function gql(source: "\n  query GetRoadQualityGrid($zoom: Int!, $bbox: [Float!]) {\n    roadQualityGrid(zoom: $zoom, bbox: $bbox)\n  }\n"): (typeof documents)["\n  query GetRoadQualityGrid($zoom: Int!, $bbox: [Float!]) {\n    roadQualityGrid(zoom: $zoom, bbox: $bbox)\n  }\n"];
/**
 * The gql function is used to parse GraphQL queries into a document that can be used by GraphQL clients.
 */
export function gql(source: "\n  query GetPointDetail($id: Int!) {\n    point(id: $id) {\n      id\n      latitude\n      longitude\n      rqiScore\n      dinoRqiScore\n      dinoScore\n      dinoPBad\n      rqiSource\n      heading\n      pitch\n      imageUrl\n      streetViewUrl\n      captureDate\n      # manual data\n      manualRqi\n      manualTags\n      manualAnnotations\n# ...\n      # analysis\n      damageCount\n      damageTypes\n      analysisMetadata\n      createdAt\n    }\n  }\n"): (typeof documents)["\n  query GetPointDetail($id: Int!) {\n    point(id: $id) {\n      id\n      latitude\n      longitude\n      rqiScore\n      dinoRqiScore\n      dinoScore\n      dinoPBad\n      rqiSource\n      heading\n      pitch\n      imageUrl\n      streetViewUrl\n      captureDate\n      # manual data\n      manualRqi\n      manualTags\n      manualAnnotations\n# ...\n      # analysis\n      damageCount\n      damageTypes\n      analysisMetadata\n      createdAt\n    }\n  }\n"];
/**
 * The gql function is used to parse GraphQL queries into a document that can be used by GraphQL clients.
 */
export function gql(source: "\n  query RouteAlternatives($origin: String!, $destination: String!) {\n    routeAlternatives(origin: $origin, destination: $destination) {\n      fastestIndex\n      smoothestIndex\n      routes {\n        index\n        distanceM\n        durationS\n        summary\n        coverage\n        isFastest\n        isSmoothest\n        points {\n          lat\n          lng\n        }\n        quality {\n          totalLengthM\n          coveredLengthM\n          lengthByRqi\n          meanScore\n          meanRqi\n          impactScore\n        }\n      }\n    }\n  }\n"): (typeof documents)["\n  query RouteAlternatives($origin: String!, $destination: String!) {\n    routeAlternatives(origin: $origin, destination: $destination) {\n      fastestIndex\n      smoothestIndex\n      routes {\n        index\n        distanceM\n        durationS\n        summary\n        coverage\n        isFastest\n        isSmoothest\n        points {\n          lat\n          lng\n        }\n        quality {\n          totalLengthM\n          coveredLengthM\n          lengthByRqi\n          meanScore\n          meanRqi\n          impactScore\n        }\n      }\n    }\n  }\n"];
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
export function gql(source: "\n  query GetRoadSegments($bbox: [Float!]!, $zoom: Int!) {\n    roadSegments(bbox: $bbox, zoom: $zoom) {\n      id\n      path\n      rqi\n      score\n      pBad\n      confidence\n      confidenceLevel\n      confidenceReason\n      nImages\n      lengthM\n      roadName\n      highway\n      captureDateMin\n      captureDateMax\n    }\n  }\n"): (typeof documents)["\n  query GetRoadSegments($bbox: [Float!]!, $zoom: Int!) {\n    roadSegments(bbox: $bbox, zoom: $zoom) {\n      id\n      path\n      rqi\n      score\n      pBad\n      confidence\n      confidenceLevel\n      confidenceReason\n      nImages\n      lengthM\n      roadName\n      highway\n      captureDateMin\n      captureDateMax\n    }\n  }\n"];
/**
 * The gql function is used to parse GraphQL queries into a document that can be used by GraphQL clients.
 */
export function gql(source: "\n  query GetRouteQuality($path: [[Float!]!]!) {\n    routeQuality(path: $path) {\n      totalLengthM\n      coveredLengthM\n      lengthByRqi\n      meanScore\n      impactScore\n      meanRqi\n      worstSegments {\n        id\n        path\n        rqi\n        score\n        pBad\n        confidence\n        confidenceLevel\n        confidenceReason\n        nImages\n        lengthM\n        roadName\n        highway\n        captureDateMin\n        captureDateMax\n      }\n    }\n  }\n"): (typeof documents)["\n  query GetRouteQuality($path: [[Float!]!]!) {\n    routeQuality(path: $path) {\n      totalLengthM\n      coveredLengthM\n      lengthByRqi\n      meanScore\n      impactScore\n      meanRqi\n      worstSegments {\n        id\n        path\n        rqi\n        score\n        pBad\n        confidence\n        confidenceLevel\n        confidenceReason\n        nImages\n        lengthM\n        roadName\n        highway\n        captureDateMin\n        captureDateMax\n      }\n    }\n  }\n"];
/**
 * The gql function is used to parse GraphQL queries into a document that can be used by GraphQL clients.
 */
export function gql(source: "\n  query GetSegmentFrames($segmentId: ID!) {\n    segmentFrames(segmentId: $segmentId) {\n      id\n      latitude\n      longitude\n      rqiScore\n      rqiSource\n      heading\n      captureDate\n    }\n  }\n"): (typeof documents)["\n  query GetSegmentFrames($segmentId: ID!) {\n    segmentFrames(segmentId: $segmentId) {\n      id\n      latitude\n      longitude\n      rqiScore\n      rqiSource\n      heading\n      captureDate\n    }\n  }\n"];
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
export function gql(source: "\n  query GetRqiModelInfo {\n    rqiModelInfo {\n      available\n      version\n      backbone\n      recipe\n      head\n      nTrain\n      qwk\n      mae\n      exactAcc\n      badRoadAcc\n      badRoadAuc\n      scaleMeaning\n      metricsSource\n      metricsProtocol\n      metricsMeasuredOn\n      segmentQwk\n      segmentLengthM\n      newAreaQwk\n    }\n  }\n"): (typeof documents)["\n  query GetRqiModelInfo {\n    rqiModelInfo {\n      available\n      version\n      backbone\n      recipe\n      head\n      nTrain\n      qwk\n      mae\n      exactAcc\n      badRoadAcc\n      badRoadAuc\n      scaleMeaning\n      metricsSource\n      metricsProtocol\n      metricsMeasuredOn\n      segmentQwk\n      segmentLengthM\n      newAreaQwk\n    }\n  }\n"];
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