import React from 'react'
import { BrowserRouter } from 'react-router-dom'
import { LocationListener } from '../modules/routing'
import { useAppStart, useApp } from '../modules/app'
import Routes from './Routes'
import FloatingNav from './FloatingNav'
import GlobalLoader from './GlobalLoader'


const AppContent: React.FC = () => {
  useAppStart()
  const app = useApp()

  if (app.loading) {
    return <div style={{ color: 'white', padding: 20 }}>Loading...</div>
  }

  return (
    <div className="app-layout" style={{ overflowY: 'auto', height: '100vh', width: '100vw' }}>
      <LocationListener />
      <GlobalLoader />
      <FloatingNav />
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
