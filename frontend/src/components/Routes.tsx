import React from 'react'
import { Routes as RouterRoutes, Route } from 'react-router-dom'
import HomePage from './HomePage'
import { TrainingView } from '../modules/training'
import { ROUTES } from '../routes'

const Routes: React.FC = () => {
  return (
    <RouterRoutes>
      <Route path={ROUTES.HOME.path} element={<HomePage />} />
      <Route path={ROUTES.TRAINING.path} element={<TrainingView />} />
    </RouterRoutes>
  )
}

export default Routes
