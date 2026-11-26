import { describe, it, expect } from 'vitest'
import reducer, { actions } from './slice'
import type { Annotation, TrainingPoint, TrainingState, TrainingStats } from './types'

const initial: TrainingState = reducer(undefined, { type: '@@INIT' })

const poly = (id: string, x: number, score?: number): Annotation => ({
  id,
  label: 'pothole',
  type: 'polygon',
  points: [
    [x, 0],
    [x + 10, 0],
    [x + 10, 10],
    [x, 10],
  ],
  score,
})

const rejected = (type: string, error: { name?: string; message?: string }) => ({ type, error })

describe('training slice — annotation editing', () => {
  it('adds, updates and removes annotations by id', () => {
    let s = reducer(initial, actions.addAnnotation(poly('a', 0)))
    s = reducer(s, actions.setAutoDetections([poly('b', 100), poly('c', 200)]))
    expect(s.annotations.map(a => a.id)).toEqual(['a', 'b', 'c'])

    s = reducer(s, actions.updateAnnotation({ ...poly('b', 100), label: 'patch' }))
    expect(s.annotations[1].label).toBe('patch')

    // Updating an unknown id is a no-op.
    const before = s.annotations
    s = reducer(s, actions.updateAnnotation(poly('zzz', 0)))
    expect(s.annotations).toEqual(before)

    s = reducer(s, actions.removeAnnotation('a'))
    expect(s.annotations.map(a => a.id)).toEqual(['b', 'c'])
  })

  it('filters overlapping annotations with NMS, keeping the higher score', () => {
    let s = reducer(initial, actions.setAutoDetections([poly('weak', 1, 0.3), poly('strong', 0, 0.9), poly('far', 500, 0.1)]))
    s = reducer(s, actions.filterCurrentAnnotations(0.3))
    expect(s.annotations.map(a => a.id)).toEqual(['strong', 'far'])
  })

  it('leaves an empty annotation list untouched when filtering', () => {
    const s = reducer(initial, actions.filterCurrentAnnotations(0.3))
    expect(s.annotations).toEqual([])
  })
})

describe('training slice — rating form', () => {
  it('sets tool, RQI, comment and detection settings', () => {
    let s = reducer(initial, actions.setTool('patch'))
    s = reducer(s, actions.setRqi(3))
    s = reducer(s, actions.setComment('árnyékos'))
    s = reducer(s, actions.setAutoDetectConf(0.42))
    s = reducer(s, actions.setAutoDetectClasses(['pothole']))
    expect(s).toMatchObject({
      selectedTool: 'patch',
      manualRqi: 3,
      manualComment: 'árnyékos',
      autoDetectConf: 0.42,
      autoDetectClasses: ['pothole'],
    })
  })

  it('never stores the same tag twice', () => {
    let s = reducer(initial, actions.addTag('wet'))
    s = reducer(s, actions.addTag('wet'))
    s = reducer(s, actions.addTag('shadow'))
    expect(s.tags).toEqual(['wet', 'shadow'])
    s = reducer(s, actions.removeTag('wet'))
    expect(s.tags).toEqual(['shadow'])
  })

  it('setSettings overwrites only the fields that are present', () => {
    let s = reducer(initial, actions.setSettings({ rqi: 2, tags: ['wet'], comment: 'ok' }))
    expect(s).toMatchObject({ manualRqi: 2, tags: ['wet'], manualComment: 'ok' })

    // A partial payload (as the saga sends on undo) keeps the other fields.
    s = reducer(s, actions.setSettings({ rqi: null } as unknown as { rqi: number | null; tags: string[]; comment: string }))
    expect(s).toMatchObject({ manualRqi: null, tags: ['wet'], manualComment: 'ok' })
  })
})

describe('training slice — image loading', () => {
  const pendingImage = (id: number) => ({ type: actions.fetchImage.pending.type, meta: { arg: id } })

  it('clears the per-image state when a different image starts loading', () => {
    let s: TrainingState = {
      ...initial,
      imageId: '7',
      imageUrl: '/images/7.jpg',
      annotations: [poly('a', 0)],
      manualRqi: 4,
      tags: ['wet'],
      manualComment: 'x',
      previewUrl: '/previews/7.jpg',
      error: 'old',
    }
    s = reducer(s, pendingImage(8))
    expect(s).toMatchObject({
      imageId: '8',
      imageUrl: null,
      annotations: [],
      manualRqi: null,
      tags: [],
      manualComment: '',
      previewUrl: null,
      loading: true,
      error: null,
    })
  })

  it('keeps unsaved edits when the same image is re-fetched', () => {
    let s: TrainingState = { ...initial, imageId: '7', annotations: [poly('a', 0)], manualRqi: 4 }
    s = reducer(s, pendingImage(7))
    expect(s.annotations).toHaveLength(1)
    expect(s.manualRqi).toBe(4)
    expect(s.loading).toBe(true)
  })

  it('stores the fetched image with its saved labels', () => {
    const s = reducer(
      { ...initial, loading: true },
      {
        type: actions.fetchImage.fulfilled.type,
        payload: { url: '/images/8.jpg', manualRqi: 2, tags: ['wet'], annotations: [poly('a', 0)], manualComment: 'jó' },
      },
    )
    expect(s).toMatchObject({ loading: false, imageUrl: '/images/8.jpg', manualRqi: 2, tags: ['wet'], manualComment: 'jó', error: null })
    expect(s.annotations).toHaveLength(1)
  })

  it('does not wipe the form when the image has no saved labels', () => {
    const s = reducer(
      { ...initial, manualRqi: 3, manualComment: 'draft' },
      {
        type: actions.fetchImage.fulfilled.type,
        payload: { url: '/images/9.jpg', manualRqi: null, tags: null, annotations: null, manualComment: null },
      },
    )
    expect(s).toMatchObject({ imageUrl: '/images/9.jpg', manualRqi: 3, manualComment: 'draft' })
  })

  it('reports a fetch error but stays quiet about cancelled requests', () => {
    let s = reducer({ ...initial, loading: true }, rejected(actions.fetchImage.rejected.type, { message: 'boom' }))
    expect(s).toMatchObject({ loading: false, error: 'boom' })

    s = reducer({ ...initial, loading: true }, rejected(actions.fetchImage.rejected.type, {}))
    expect(s.error).toBe('Failed to fetch image')

    s = reducer({ ...initial, loading: true }, rejected(actions.fetchImage.rejected.type, { name: 'AbortError', message: 'x' }))
    expect(s).toMatchObject({ loading: false, error: null })

    s = reducer({ ...initial, loading: true }, rejected(actions.fetchImage.rejected.type, { message: 'Aborted' }))
    expect(s.error).toBeNull()
  })
})

describe('training slice — saving', () => {
  it('snapshots the form optimistically, then adopts what the server stored', () => {
    let s: TrainingState = { ...initial, manualRqi: 3, tags: ['wet'], manualComment: 'c' }
    s = reducer(s, { type: actions.saveAnnotations.pending.type })
    expect(s.saving).toBe(true)
    expect(s.lastSavedSettings).toEqual({ rqi: 3, tags: ['wet'], comment: 'c' })

    s = reducer(s, { type: actions.saveAnnotations.fulfilled.type, payload: { rqi: 2, tags: ['dry'], comment: 'd' } })
    expect(s.saving).toBe(false)
    expect(s.lastSavedSettings).toEqual({ rqi: 2, tags: ['dry'], comment: 'd' })
  })

  it('keeps the optimistic snapshot when the save returns nothing', () => {
    let s = reducer({ ...initial, manualRqi: 1 }, { type: actions.saveAnnotations.pending.type })
    s = reducer(s, { type: actions.saveAnnotations.fulfilled.type, payload: undefined })
    expect(s.lastSavedSettings).toEqual({ rqi: 1, tags: [], comment: '' })
  })

  it('surfaces a save failure', () => {
    let s = reducer({ ...initial, saving: true }, rejected(actions.saveAnnotations.rejected.type, { message: 'disk full' }))
    expect(s).toMatchObject({ saving: false, error: 'disk full' })
    s = reducer({ ...initial, saving: true }, rejected(actions.saveAnnotations.rejected.type, {}))
    expect(s.error).toBe('Saving failed')
  })
})

describe('training slice — list paging', () => {
  const item = (id: number): TrainingPoint => ({ id, createdAt: '2026-01-01', latitude: 47.5, longitude: 19 })
  const listMeta = (arg: { mode: string; offset?: number }) => ({ arg })

  it('resets the list on the first page but keeps it while paging', () => {
    const loaded: TrainingState = {
      ...initial,
      items: [item(1)],
      offset: 20,
      hasMore: true,
      totalCount: 99,
      navigationIds: ['1'],
    }
    const paging = reducer(loaded, { type: actions.fetchList.pending.type, meta: listMeta({ mode: 'all', offset: 20 }) })
    expect(paging.items).toHaveLength(1)
    expect(paging.loading).toBe(true)

    const first = reducer(loaded, { type: actions.fetchList.pending.type, meta: listMeta({ mode: 'all' }) })
    expect(first).toMatchObject({ items: [], offset: 0, hasMore: false, totalCount: 0, navigationIds: [] })
  })

  it('stores a page, its navigation ids and the lower-cased mode', () => {
    const s = reducer(initial, {
      type: actions.fetchList.fulfilled.type,
      payload: { items: [item(4), item(5)], totalCount: 42, hasMore: true },
      meta: listMeta({ mode: 'PENDING', offset: 20 }),
    })
    expect(s).toMatchObject({
      loading: false,
      totalCount: 42,
      hasMore: true,
      offset: 20,
      navigationIds: ['4', '5'],
      activeMode: 'pending',
    })
  })

  it('falls back to offset 0 and mode "all"', () => {
    const s = reducer(initial, {
      type: actions.fetchList.fulfilled.type,
      payload: { items: [], totalCount: 0, hasMore: false },
      meta: listMeta({ mode: '' }),
    })
    expect(s).toMatchObject({ offset: 0, activeMode: 'all', navigationIds: [] })
  })

  it('surfaces a list failure and stores fetched stats', () => {
    let s = reducer({ ...initial, loading: true }, rejected(actions.fetchList.rejected.type, {}))
    expect(s).toMatchObject({ loading: false, error: 'Failed to fetch list' })

    const stats = { total: 10, pending: 4, annotated: 6 } as TrainingStats
    s = reducer(s, { type: actions.fetchStats.fulfilled.type, payload: stats })
    expect(s.globalStats).toBe(stats)
  })
})

describe('training slice — review actions and jobs', () => {
  it('tracks which review action is running', () => {
    let s = reducer(
      { ...initial, error: 'old' },
      { type: actions.performReviewAction.pending.type, meta: { arg: { actionType: 'auto_detect', params: {} } } },
    )
    expect(s).toMatchObject({ loadingAction: 'auto_detect', error: null })

    s = reducer(initial, { type: actions.performReviewAction.pending.type, meta: {} })
    expect(s.loadingAction).toBe('unknown')
  })

  it('appends detections and shows the processed preview', () => {
    let s = reducer(
      { ...initial, loadingAction: 'auto_detect', annotations: [poly('a', 0)] },
      { type: actions.performReviewAction.fulfilled.type, payload: { annotations: [poly('b', 50)], processedImageUrl: '/previews/1.jpg' } },
    )
    expect(s.loadingAction).toBeNull()
    expect(s.annotations.map(a => a.id)).toEqual(['a', 'b'])
    expect(s.previewUrl).toBe('/previews/1.jpg')

    s = reducer(s, actions.clearPreview())
    expect(s.previewUrl).toBeNull()

    // A message-only result changes neither annotations nor preview.
    s = reducer(s, { type: actions.performReviewAction.fulfilled.type, payload: { message: 'ok' } })
    expect(s.annotations).toHaveLength(2)
    expect(s.previewUrl).toBeNull()
  })

  it('surfaces a failed review action', () => {
    let s = reducer({ ...initial, loadingAction: 'x' }, rejected(actions.performReviewAction.rejected.type, { message: 'nope' }))
    expect(s).toMatchObject({ loadingAction: null, error: 'nope' })
    s = reducer(initial, rejected(actions.performReviewAction.rejected.type, {}))
    expect(s.error).toBe('Action failed')
  })

  it('follows an analysis job from start to completion', () => {
    let s = reducer({ ...initial, exports: { notebookPath: 'old.ipynb' } }, { type: actions.runAnalysis.pending.type })
    expect(s.exports).toBeNull()

    s = reducer(s, { type: actions.runAnalysis.fulfilled.type, payload: { jobId: 'job-1' } })
    expect(s.analysisJobId).toBe('job-1')

    s = reducer(s, actions.jobCompleted({ exports: { datasetPath: 'data.zip' } }))
    expect(s).toMatchObject({ trainingStatus: 'completed', analysisJobId: null, exports: { datasetPath: 'data.zip' } })

    s = reducer(s, actions.jobCompleted(undefined))
    expect(s.exports).toBeNull()

    s = reducer(s, actions.setAnalysisJobId('job-2'))
    expect(s.analysisJobId).toBe('job-2')

    s = reducer(s, actions.resetAnalysisJob())
    expect(s).toMatchObject({ analysisJobId: null, exports: null, trainingStatus: 'idle' })
  })

  it('tracks the training job status', () => {
    let s = reducer(initial, { type: actions.startTraining.pending.type })
    expect(s).toMatchObject({ trainingStatus: 'running', exports: null })

    s = reducer(s, { type: actions.startTraining.fulfilled.type, payload: { jobId: 'train-1' } })
    expect(s.analysisJobId).toBe('train-1')

    s = reducer(s, { type: actions.startTraining.rejected.type })
    expect(s.trainingStatus).toBe('failed')
  })
})
