import React, { Suspense, lazy } from 'react'
import { Routes as RouterRoutes, Route } from 'react-router-dom'
import { RequireAdmin } from 'modules/auth'
import HomePage from './HomePage'
import { ROUTES } from '../routes'

// Only the map (HomePage) is in the initial bundle: anonymous visitors on a
// phone never download the admin pages (training/review, quick-rate,
// settings, admin stats). Each page is its own chunk, fetched on navigation.
const TrainingPage = lazy(() => import('./pages/TrainingPage'))
const TrainingDashboardPage = lazy(() => import('./pages/TrainingDashboardPage'))
const SettingsPage = lazy(() => import('./pages/SettingsPage'))
const AdminStatsPage = lazy(() => import('./pages/AdminStatsPage'))
const QuickLabelPage = lazy(() => import('./pages/QuickLabelPage'))

const PageFallback: React.FC = () => (
  <div role="status" style={{ color: '#9ca3af', padding: 20, fontSize: 14 }}>
    Betöltés…
  </div>
)

const AdminPage: React.FC<{ children: React.ReactElement }> = ({ children }) => (
  <RequireAdmin>
    <Suspense fallback={<PageFallback />}>{children}</Suspense>
  </RequireAdmin>
)

const Routes: React.FC = () => {
  return (
    <RouterRoutes>
      <Route path={ROUTES.HOME.path} element={<HomePage />} />
      <Route path={ROUTES.TRAINING_LIST.path} element={<AdminPage><TrainingDashboardPage /></AdminPage>} />
      <Route path={ROUTES.QUICK_LABEL.path} element={<AdminPage><QuickLabelPage /></AdminPage>} />
      <Route path={ROUTES.TRAINING_REVIEW.path} element={<AdminPage><TrainingPage /></AdminPage>} />
      <Route path={ROUTES.SETTINGS.path} element={<AdminPage><SettingsPage /></AdminPage>} />
      <Route path={ROUTES.ADMIN.path} element={<AdminPage><AdminStatsPage /></AdminPage>} />
    </RouterRoutes>
  )
}

export default Routes
