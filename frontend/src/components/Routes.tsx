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

class AdminErrorBoundary extends React.Component<
  { children: React.ReactNode },
  { failed: boolean }
> {
  state = { failed: false }

  static getDerivedStateFromError() {
    return { failed: true }
  }

  render() {
    if (this.state.failed) {
      return (
        <div role="alert" style={{ color: '#d1d5db', padding: 20, fontSize: 14 }}>
          <p>Nem sikerült betölteni az oldalt.</p>
          <button
            type="button"
            className="fnav-btn"
            onClick={() => window.location.reload()}
            style={{
              padding: '10px 16px',
              borderRadius: '9999px',
              border: '1px solid rgba(255, 255, 255, 0.1)',
              background: 'rgba(0, 0, 0, 0.4)',
              color: 'inherit',
              cursor: 'pointer',
              fontSize: 'inherit',
              fontWeight: 500,
            }}>
            Újratöltés
          </button>
        </div>
      )
    }
    return this.props.children
  }
}

const AdminPage: React.FC<{ children: React.ReactElement }> = ({ children }) => (
  <RequireAdmin>
    <AdminErrorBoundary>
      <Suspense fallback={<PageFallback />}>{children}</Suspense>
    </AdminErrorBoundary>
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
