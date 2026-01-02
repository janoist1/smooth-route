import React from 'react'
import { Routes as RouterRoutes, Route } from 'react-router-dom'
import HomePage from './HomePage'
import { TrainingView, TrainingDashboard } from '../modules/training'
import { ROUTES } from '../routes'

const Routes: React.FC = () => {
  return (
    <RouterRoutes>
      <Route path={ROUTES.HOME.path} element={<HomePage />} />
      <Route path={ROUTES.TRAINING_LIST.path} element={<TrainingDashboard />} />
      <Route path={ROUTES.TRAINING_DETAIL.path} element={<TrainingView />} />
      <Route path={ROUTES.TRAINING_REVIEW.path} element={<TrainingView reviewMode={true} />} />
    </RouterRoutes>
  )
}

export default Routes
