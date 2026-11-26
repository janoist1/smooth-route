import type { SagaIterator } from 'redux-saga'
import { call, fork, put, select, take, takeEvery, takeLatest } from 'redux-saga/effects'
import { takeLatestAsync } from 'saga-toolkit'
import { gql, gqlMutate, gqlQuery } from '../graphql'
import { excludeIds, needsRefill, QUEUE_BATCH, saveSkipped, saveStrategy } from './logic'
import { selectRoot } from './selectors'
import {
  enter,
  fetchExamples,
  fetchQueue,
  rate,
  setStrategy,
  skip,
  undoLast,
  writeDone,
  writeFailed,
} from './slice'
import type { LabelExample, LabelingState, LabelQueuePage, OutboxWrite } from './types'

const LABEL_QUEUE = gql(`
  query LabelQueue($strategy: LabelQueueStrategy!, $limit: Int!, $excludeIds: [Int!]) {
    labelQueue(strategy: $strategy, limit: $limit, excludeIds: $excludeIds) {
      strategy
      items {
        id
        imageUrl
        latitude
        longitude
        heading
        captureDate
        streetViewUrl
        reason
        area
        uncertainty
        cellLabels
        boundary
        modelScore
        modelRqi
        modelPBad
      }
      stats {
        totalLabelled
        labelledToday
        eligible
        scored
        rechecked
        recheckSame
        recheckWithinOne
      }
    }
  }
`)

const LABEL_EXAMPLES = gql(`
  query LabelExamples($perClass: Int!) {
    labelExamples(perClass: $perClass) {
      rqi
      id
      imageUrl
    }
  }
`)

const QUICK_LABEL = gql(`
  mutation QuickLabel($input: QuickLabelInput!) {
    quickLabel(input: $input) {
      pointId
      rqi
      totalLabelled
      labelledToday
    }
  }
`)

const UNDO_QUICK_LABEL = gql(`
  mutation UndoQuickLabel($pointId: Int!) {
    undoQuickLabel(pointId: $pointId)
  }
`)

const errorText = (e: unknown): string => (e instanceof Error ? e.message : String(e))

function* enterWorker() {
  const state: LabelingState = yield select(selectRoot)
  if (state.examples.length === 0) yield put(fetchExamples())
  if (state.queue.length === 0 && !state.loading) yield put(fetchQueue())
}

function* fetchQueueWorker() {
  const state: LabelingState = yield select(selectRoot)
  const data = yield* gqlQuery({
    query: LABEL_QUEUE,
    variables: {
      strategy: state.strategy,
      limit: QUEUE_BATCH,
      excludeIds: excludeIds(state.queue, state.history, state.skipped),
    },
    fetchPolicy: 'network-only',
  })
  return data.labelQueue as LabelQueuePage
}

function* fetchExamplesWorker() {
  const data = yield* gqlQuery({ query: LABEL_EXAMPLES, variables: { perClass: 1 } })
  return data.labelExamples as LabelExample[]
}

function* sendWrite(write: OutboxWrite): SagaIterator<void> {
  try {
    if (write.kind === 'save') {
      yield* gqlMutate({
        mutation: QUICK_LABEL,
        variables: {
          input: {
            pointId: write.id,
            rqi: write.rqi,
            strategy: write.strategy.toLowerCase(),
            reason: write.reason,
            revealedModel: write.revealed,
            elapsedMs: write.elapsedMs == null ? null : Math.round(write.elapsedMs),
          },
        },
      })
    } else {
      yield* gqlMutate({ mutation: UNDO_QUICK_LABEL, variables: { pointId: write.id } })
    }
    yield put(writeDone({ seq: write.seq }))
  } catch (e) {
    yield put(writeFailed({ seq: write.seq, message: errorText(e) }))
  }
}

/**
 * Drains the outbox strictly in order, one write at a time: the server must
 * see "rate A=2, undo A, rate A=4" exactly like that. In parallel, a slow
 * save could land after its undo and the stored label would not match the
 * screen.
 */
function* labelWriter(): SagaIterator<void> {
  while (true) {
    const state: LabelingState = yield select(selectRoot)
    const next = state.outbox[0]
    if (next) yield call(sendWrite, next)
    else yield take([rate.type, undoLast.type])
  }
}

function* refillWorker(): SagaIterator<void> {
  const state: LabelingState = yield select(selectRoot)
  if (needsRefill(state.queue.length, state.loading, state.exhausted)) yield put(fetchQueue())
}

function* persistSkipped(): SagaIterator<void> {
  const state: LabelingState = yield select(selectRoot)
  yield call(saveSkipped, state.skipped)
}

function* persistStrategy(action: ReturnType<typeof setStrategy>): SagaIterator<void> {
  yield call(saveStrategy, action.payload)
}

export default [
  takeLatestAsync(enter, enterWorker),
  takeLatestAsync(fetchQueue, fetchQueueWorker),
  takeLatestAsync(fetchExamples, fetchExamplesWorker),
  fork(labelWriter),
  takeLatest(
    [rate.type, skip.type, undoLast.type, setStrategy.type, writeFailed.type, fetchQueue.fulfilled.type],
    refillWorker,
  ),
  takeEvery([skip.type, undoLast.type], persistSkipped),
  takeEvery(setStrategy.type, persistStrategy),
]
