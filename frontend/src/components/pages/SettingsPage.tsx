import React from 'react'
import { Loader2, Save } from 'lucide-react'
import { useSettings, SettingsHeader, SettingsList, ModelCard } from 'modules/settings'
import MainLayout from '../MainLayout'

const SettingsPage: React.FC = () => {
  const { items, loading, saveLoading, error, categories, updateSetting } = useSettings()

  const handleUpdate = (key: string, value: unknown) => {
    updateSetting({ key, value })
  }

  if (loading && items.length === 0) {
    return (
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          height: '100vh',
          background: '#111',
        }}>
        <Loader2 className="animate-spin" size={40} color="#3b82f6" />
        <style>{`
          .animate-spin { animation: spin 1s linear infinite; }
          @keyframes spin { 100% { transform: rotate(360deg); } }
        `}</style>
      </div>
    )
  }

  return (
    <MainLayout>
      <div
        style={{ padding: '40px', maxWidth: '1200px', margin: '0 auto', paddingBottom: '120px' }}>
        <SettingsHeader />

        <ModelCard />

        {error && (
          <div
            style={{
              background: 'rgba(239, 68, 68, 0.1)',
              borderColor: 'rgba(239, 68, 68, 0.2)',
              borderWidth: '1px',
              borderStyle: 'solid',
              color: '#f87171',
              padding: '16px 20px',
              borderRadius: '16px',
              marginBottom: '48px',
              display: 'flex',
              alignItems: 'center',
              gap: '12px',
            }}>
            <span style={{ fontSize: '1.2rem' }}>⚠️</span>
            {error}
          </div>
        )}

        <SettingsList
          items={items}
          categories={categories}
          saveLoading={saveLoading}
          onUpdate={handleUpdate}
        />
      </div>

      {saveLoading && (
        <div
          style={{
            position: 'fixed',
            bottom: '40px',
            right: '40px',
            background: 'rgba(59, 130, 246, 0.95)',
            backdropFilter: 'blur(12px)',
            color: 'white',
            padding: '16px 32px',
            borderRadius: '20px',
            boxShadow: '0 20px 25px -5px rgba(0, 0, 0, 0.3), 0 10px 10px -5px rgba(0, 0, 0, 0.1)',
            display: 'flex',
            alignItems: 'center',
            gap: '16px',
            zIndex: 100,
            borderColor: 'rgba(255,255,255,0.2)',
            borderWidth: '1px',
            borderStyle: 'solid',
            animation: 'slideUp 0.3s cubic-bezier(0.16, 1, 0.3, 1)',
          }}>
          <Save size={20} />
          <span style={{ fontWeight: 600, fontSize: '1rem' }}>Mentés folyamatban...</span>
          <style>{`
             @keyframes slideUp { 0% { opacity: 0; transform: translateY(20px); } 100% { opacity: 1; transform: translateY(0); } }
             .hover-lift:hover { transform: translateY(-4px); border-color: rgba(59, 130, 246, 0.3) !important; }
             .preset-btn:hover { background: rgba(59, 130, 246, 0.2) !important; transform: scale(1.02); }
           `}</style>
        </div>
      )}
    </MainLayout>
  )
}

export default SettingsPage
