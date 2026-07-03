import React from 'react'
import { Routes as RouterRoutes, Route } from 'react-router-dom'
import { RequireAdmin } from 'modules/auth'
import HomePage from './HomePage'
import TrainingPage from './pages/TrainingPage'
import TrainingDashboardPage from './pages/TrainingDashboardPage'
import SettingsPage from './pages/SettingsPage'
import { ROUTES } from '../routes'

const Routes: React.FC = () => {
  return (
    <RouterRoutes>
      <Route path={ROUTES.HOME.path} element={<HomePage />} />
      <Route
        path={ROUTES.TRAINING_LIST.path}
        element={
          <RequireAdmin>
            <TrainingDashboardPage />
          </RequireAdmin>
        }
      />
      <Route
        path={ROUTES.TRAINING_REVIEW.path}
        element={
          <RequireAdmin>
            <TrainingPage />
          </RequireAdmin>
        }
      />
      <Route
        path={ROUTES.SETTINGS.path}
        element={
          <RequireAdmin>
            <SettingsPage />
          </RequireAdmin>
        }
      />
    </RouterRoutes>
  )
}

export default Routes
