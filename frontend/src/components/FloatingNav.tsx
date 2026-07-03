import React from 'react'
import { useNavigate, useLocation } from 'react-router-dom'
import { Map as MapIcon, Database, Settings, BarChart3 } from 'lucide-react'
import { FloatingNavBar } from 'modules/ui'
import { UserMenu, useViewer } from 'modules/auth'

const FloatingNav: React.FC = () => {
  const navigate = useNavigate()
  const location = useLocation()
  const { isAdmin } = useViewer()

  const navItems = [
    { path: '/', label: 'Map', icon: <MapIcon size={20} /> },
    // Training/Settings are admin-only surfaces; the backend enforces the
    // same rule, hiding them here is just honest navigation.
    ...(isAdmin
      ? [
          { path: '/admin', label: 'Admin', icon: <BarChart3 size={20} /> },
          { path: '/training', label: 'Training', icon: <Database size={20} /> },
          { path: '/settings', label: 'Settings', icon: <Settings size={20} /> },
        ]
      : []),
  ]

  return (
    <FloatingNavBar
      items={navItems}
      currentPath={location.pathname}
      onNavigate={(path: string) => navigate(path)}
      trailing={<UserMenu />}
    />
  )
}

export default FloatingNav
