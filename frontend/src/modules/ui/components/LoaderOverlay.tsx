import React from 'react'

export const LoaderOverlay: React.FC = () => (
  <div
    style={{
      position: 'absolute',
      inset: 0,
      zIndex: 150,
      background: '#111',
      display: 'flex',
      flexDirection: 'column',
      alignItems: 'center',
      justifyContent: 'center',
      color: 'white',
    }}>
    <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-500 mb-4"></div>
    <div className="text-lg font-medium">Loading Training Data...</div>
  </div>
)
