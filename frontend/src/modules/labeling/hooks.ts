import { useCallback, useEffect, useMemo, useRef } from 'react'
import { useDispatch, useSelector } from 'react-redux'
import { bindActionCreators } from '@reduxjs/toolkit'
import { canUndo, newClientId, prefetchUrls, retrainMilestone } from './logic'
import { selectRoot } from './selectors'
import { actions } from './slice'
import type { LabelMode, LabelStrategy, PairResult } from './types'

/** Warm the browser cache with the next frames so each rating is instant. */
const usePrefetch = (urls: string[]) => {
  const key = urls.join('|')
  const held = useRef<HTMLImageElement[]>([])
  useEffect(() => {
    // Keep references until the next batch so the requests are not dropped.
    held.current = key
      ? key.split('|').map(url => {
          const img = new Image()
          img.decoding = 'async'
          img.src = url
          return img
        })
      : []
  }, [key])
}

/** Controller for the quick-rate screen ("Gyors címkézés"). */
export const useQuickLabel = () => {
  const dispatch = useDispatch()
  // Saga actions (thunk-shaped) are bound like in the settings module.
  const async = useMemo(() => bindActionCreators({ fetchQueue: actions.fetchQueue }, dispatch), [dispatch])
  const state = useSelector(selectRoot)
  const current = state.queue[0] ?? null

  // Time on screen per frame (stored with the label for later analysis).
  const shownAt = useRef<{ id: number | null; t0: number }>({ id: null, t0: 0 })
  useEffect(() => {
    shownAt.current = { id: current?.id ?? null, t0: performance.now() }
  }, [current?.id])

  usePrefetch(useMemo(() => prefetchUrls(state.queue), [state.queue]))

  // Pairwise mode: same timing + double-tap guard (aId) as rating.
  const currentPair = state.pairs[0] ?? null
  const pairShownAt = useRef<{ id: number | null; t0: number }>({ id: null, t0: 0 })
  useEffect(() => {
    pairShownAt.current = { id: currentPair?.a.id ?? null, t0: performance.now() }
  }, [currentPair?.a.id])
  usePrefetch(
    useMemo(
      () => state.pairs.slice(1, 3).flatMap(p => [p.a, p.b]).map(it => (it.imageUrl.startsWith('/') ? it.imageUrl : `/${it.imageUrl}`)),
      [state.pairs],
    ),
  )
  const judge = useCallback(
    (result: PairResult) => {
      if (!currentPair) return
      const elapsedMs =
        pairShownAt.current.id === currentPair.a.id ? performance.now() - pairShownAt.current.t0 : undefined
      dispatch(actions.judgePair({ aId: currentPair.a.id, result, clientId: newClientId(), elapsedMs }))
    },
    [currentPair, dispatch],
  )

  const rate = useCallback(
    (rqi: number) => {
      if (!current) return
      const elapsedMs = shownAt.current.id === current.id ? performance.now() - shownAt.current.t0 : undefined
      dispatch(actions.rate({ id: current.id, rqi, elapsedMs }))
    },
    [current, dispatch],
  )

  const skip = useCallback(() => {
    if (current) dispatch(actions.skip({ id: current.id }))
  }, [current, dispatch])

  const undoable = canUndo(state.history)
  const undo = useCallback(() => {
    dispatch(actions.undoLast())
  }, [dispatch])

  return {
    current,
    queueLength: state.queue.length,
    strategy: state.strategy,
    stats: state.stats,
    sessionRated: state.sessionRated,
    examples: state.examples,
    loading: state.loading,
    exhausted: state.exhausted,
    error: state.error,
    reveal: state.reveal,
    lastResult: state.lastResult,
    canUndo: undoable,
    mode: state.mode,
    setMode: (m: LabelMode) => dispatch(actions.setMode(m)),
    currentPair,
    pairsJudged: state.pairsJudged,
    pairsLoading: state.pairsLoading,
    pairsExhausted: state.pairsExhausted,
    judge,
    undoPair: () => dispatch(actions.undoPair()),
    canUndoPair: state.pairHistory.length > 0,
    retrainMilestone: retrainMilestone(state.stats?.sprintLabelled, state.retrainAck),
    ackRetrain: (m: number) => dispatch(actions.ackRetrain(m)),
    pendingWrites: state.outbox.length,
    rate,
    skip,
    undo,
    setStrategy: (s: LabelStrategy) => dispatch(actions.setStrategy(s)),
    toggleReveal: () => dispatch(actions.toggleReveal()),
    clearError: () => dispatch(actions.clearError()),
    retry: () => async.fetchQueue(),
  }
}
