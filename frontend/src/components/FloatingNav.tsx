import React from 'react'
import { useNavigate, useLocation } from 'react-router-dom'
import { Map as MapIcon, Database, Settings } from 'lucide-react'
import { FloatingNavBar } from 'modules/ui'

const FloatingNav: React.FC = () => {
  const navigate = useNavigate()
  const location = useLocation()

  const navItems = [
    { path: '/', label: 'Map', icon: <MapIcon size={20} /> },
    { path: '/training', label: 'Training', icon: <Database size={20} /> },
    { path: '/settings', label: 'Settings', icon: <Settings size={20} /> },
  ]

  return (
    <FloatingNavBar
      items={navItems}
      currentPath={location.pathname}
      onNavigate={(path: string) => navigate(path)}
    />
  )
}

export default FloatingNav
