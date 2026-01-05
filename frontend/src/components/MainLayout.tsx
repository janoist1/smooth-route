import React from 'react'
import FloatingNav from './FloatingNav'

interface MainLayoutProps {
  children: React.ReactNode
}

const MainLayout: React.FC<MainLayoutProps> = ({ children }) => {
  return (
    <>
      <FloatingNav />
      {children}
    </>
  )
}

export default MainLayout
