import React from 'react'
import { Routes as RouterRoutes, Route } from 'react-router-dom'
import HomePage from './HomePage'
import TrainingPage from './pages/TrainingPage'
import TrainingDashboardPage from './pages/TrainingDashboardPage'
import SettingsPage from './pages/SettingsPage'
import { ROUTES } from '../routes'

const Routes: React.FC = () => {
  return (
    <RouterRoutes>
      <Route path={ROUTES.HOME.path} element={<HomePage />} />
      <Route path={ROUTES.TRAINING_LIST.path} element={<TrainingDashboardPage />} />
      <Route path={ROUTES.TRAINING_DETAIL.path} element={<TrainingPage />} />
      <Route path={ROUTES.TRAINING_REVIEW.path} element={<TrainingPage reviewMode={true} />} />
      <Route path={ROUTES.SETTINGS.path} element={<SettingsPage />} />
    </RouterRoutes>
  )
}

export default Routes
