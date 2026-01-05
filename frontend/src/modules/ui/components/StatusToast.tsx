import React from 'react'
import { Save } from 'lucide-react'

interface StatusToastProps {
  saving: boolean
  showSavedFeedback: boolean
}

export const StatusToast: React.FC<StatusToastProps> = ({ saving, showSavedFeedback }) => {
  if (!saving && !showSavedFeedback) return null

  return (
    <div
      style={{
        position: 'absolute',
        top: '20px',
        right: '80px',
        zIndex: 100,
        background: saving ? '#3498db' : '#2ecc71',
        color: 'white',
        padding: '8px 16px',
        borderRadius: '4px',
        fontSize: '13px',
        fontWeight: 600,
        boxShadow: '0 4px 12px rgba(0,0,0,0.2)',
        display: 'flex',
        alignItems: 'center',
        gap: '8px',
        transition: 'all 0.3s ease',
      }}>
      {saving ? (
        <>
          <div className="animate-spin h-4 w-4 border-2 border-white border-t-transparent rounded-full" />
          <span>Mentés...</span>
        </>
      ) : (
        <>
          <Save size={16} />
          <span>Sikeresen mentve!</span>
        </>
      )}
    </div>
  )
}
