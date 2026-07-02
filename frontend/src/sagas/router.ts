import type { SagaIterator } from 'redux-saga'
import { takeLatest, put, call, select } from 'redux-saga/effects'
import { matchPath, type PathMatch } from 'react-router-dom'
import { actions as trainingActions, selectors as trainingSelectors } from 'modules/training'
import { actions as mapActions, selectors as mapSelectors } from 'modules/map'
import { actions as settingsActions } from 'modules/settings'
import { actions as routingActions } from 'modules/routing'
import { waitForAppStart } from 'modules/app'
import { PAGE_SIZE } from '../constants'
import { ROUTES } from '../routes'
import type { TrainingPoint } from 'modules/training/types'
import type { RootState } from '../store'

// --- Route Handlers ---

// eslint-disable-next-line @typescript-eslint/no-unused-vars
function* handleTrainingDinoReview(match: PathMatch, _searchParams: URLSearchParams): SagaIterator {
  console.log('Router: Handling Dino Review', match.params)
  const pointId = match.params.id ? parseInt(match.params.id, 10) : 0
  if (pointId) yield put(trainingActions.fetchDinoImage(pointId))
}

function* handleTrainingDinoList(_match: PathMatch, searchParams: URLSearchParams): SagaIterator {
  console.log('Router: Handling Dino List', { page: searchParams.get('page'), mode: searchParams.get('mode') })
  const mode = (searchParams.get('mode') || 'all') as string
  const page = parseInt(searchParams.get('page') || '1', 10)
  const offset = (page - 1) * PAGE_SIZE

  const activeMode: string = yield select(trainingSelectors.selectActiveMode)
  const currentItems: TrainingPoint[] = yield select(trainingSelectors.selectItems)
  const currentOffset: number = yield select(trainingSelectors.selectOffset)
  const currentStats: unknown = yield select((state: RootState) => state.training.globalStats)

  // Fetch List: Mode or Offset change
  if (mode.toLowerCase() !== activeMode.toLowerCase() || currentItems.length === 0 || currentOffset !== offset) {
    yield put(trainingActions.fetchList({ offset, mode, model: 'dino' }))
  }

  // Fetch Stats: Only if Mode changed
  if (mode.toLowerCase() !== activeMode.toLowerCase() || !currentStats) {
     yield put(trainingActions.fetchStats({ mode: mode.toUpperCase(), model: 'dino' }))
  }
}

// eslint-disable-next-line @typescript-eslint/no-unused-vars
function* handleTrainingDetail(match: PathMatch, _searchParams: URLSearchParams): SagaIterator {
  const pointId = match.params.id ? parseInt(match.params.id, 10) : 0
  if (pointId) yield put(trainingActions.fetchImage(pointId))
}

function* handleTrainingDashboard(_match: PathMatch, searchParams: URLSearchParams): SagaIterator {
  const mode = (searchParams.get('mode') || 'all') as 'pending' | 'reviewed' | 'all'
  const page = parseInt(searchParams.get('page') || '1', 10)
  
  // Get current filter from state
  const activeMode: string = yield select(trainingSelectors.selectActiveMode)
  const currentItems: TrainingPoint[] = yield select(trainingSelectors.selectItems)
  const currentOffset: number = yield select(trainingSelectors.selectOffset)
  const currentStats: unknown = yield select((state: RootState) => state.training.globalStats)
  const offset = (page - 1) * PAGE_SIZE

  // Fetch List: Mode or Offset change
  if (mode.toLowerCase() !== activeMode?.toLowerCase() || currentItems.length === 0 || currentOffset !== offset) {
    yield put(trainingActions.fetchList({ mode: mode.toUpperCase(), offset }))
  }

  // Fetch Stats: Only if Mode changed
  if (mode.toLowerCase() !== activeMode?.toLowerCase() || !currentStats) {
    yield put(trainingActions.fetchStats({ mode: mode.toUpperCase(), model: 'yolo' }))
  }

  // Always check job status
  yield put(trainingActions.reconnectJob())
  yield put(settingsActions.fetchSettings())
}

function* handleMapHome(_match: PathMatch, searchParams: URLSearchParams): SagaIterator {
  // SYNC MAP URL -> REDUX
  const lat = searchParams.get('lat')
  const lng = searchParams.get('lng')
  const z = searchParams.get('z')

  if (lat && lng && z) {
    yield put(
      mapActions.setViewport({
        center: [parseFloat(lat), parseFloat(lng)],
        zoom: parseInt(z, 10),
      }),
    )
  }

  // Fetch Points (Router-driven)
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const viewport: any = yield select(mapSelectors.selectViewport)
  const { center, zoom } = viewport

  // Approximate BBox calculation
  const width = typeof window !== 'undefined' ? window.innerWidth : 1024
  const height = typeof window !== 'undefined' ? window.innerHeight : 768
  const degPerPixel = 360 / (Math.pow(2, zoom) * 256)
  const lngDelta = (width / 2) * degPerPixel
  const latDelta = (height / 2) * degPerPixel

  yield put(mapActions.fetchPoints([
    center[1] - lngDelta, center[0] - latDelta,
    center[1] + lngDelta, center[0] + latDelta,
  ]))

  // Restore a route analysis job still running on the backend (survives reload)
  yield put(mapActions.reconnectRouteJob())
}

// eslint-disable-next-line @typescript-eslint/no-unused-vars
function* handleSettings(_match: PathMatch, _searchParams: URLSearchParams): SagaIterator {
   yield put(settingsActions.fetchSettings())
}

// --- Route Configuration (Order Matters!) ---
// Specific routes first, generic routes last.
interface RouteHandlerConfig {
    route: { path: string; exact?: boolean }
    handler: (match: PathMatch, searchParams: URLSearchParams) => SagaIterator
}

const ROUTE_CONFIG: RouteHandlerConfig[] = [
  { route: ROUTES.TRAINING_DINO_REVIEW, handler: handleTrainingDinoReview },
  { route: ROUTES.TRAINING_DINO_LIST, handler: handleTrainingDinoList },
  { route: ROUTES.TRAINING_DETAIL, handler: handleTrainingDetail }, 
  { route: ROUTES.TRAINING_REVIEW, handler: handleTrainingDetail }, 
  { route: ROUTES.TRAINING_LIST, handler: handleTrainingDashboard },
  { route: ROUTES.HOME, handler: handleMapHome },
  { route: ROUTES.SETTINGS, handler: handleSettings },
]

// --- Master Orchestrator ---
function* handleLocationChange(action: { payload: { pathname: string; search: string } }): SagaIterator {
  // Blocking check: Wait for App Start
  yield call(waitForAppStart)

  const { pathname, search } = action.payload
  const searchParams = new URLSearchParams(search)

  // Iterate routes and find first match
  for (const config of ROUTE_CONFIG) {
    const match = matchPath({ path: config.route.path, end: config.route.exact }, pathname)
    if (match) {
       yield call(config.handler, match, searchParams)
       return // Stop after first match
    }
  }
}

export default [takeLatest(routingActions.locationChange, handleLocationChange)]
