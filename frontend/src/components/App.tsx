import React from 'react'
import { BrowserRouter } from 'react-router-dom'
import { LocationListener } from '../modules/routing'
import { useAppStart, useApp } from '../modules/app'
import Routes from './Routes'

const AppContent: React.FC = () => {
  useAppStart()
  const app = useApp()

  if (app.loading) {
    return <div style={{ color: 'white', padding: 20 }}>Loading...</div>
  }

  return (
    <div className="app-layout">
      <LocationListener />
      <Routes />
    </div>
  )
}

const App: React.FC = () => {
  return (
    <BrowserRouter>
      <AppContent />
    </BrowserRouter>
  )
}

export default App
