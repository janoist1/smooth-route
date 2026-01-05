import React, { useState, useEffect } from 'react'
import { Settings, BarChart3, BrainCircuit, Map as MapIcon, Wand2, Loader2 } from 'lucide-react'
import { GlassPanel, FormControl, TextInput, NumberInput, Select } from '../../ui'
import { client, gql } from '../../graphql'
import type { SystemSetting } from '..'

const GET_AVAILABLE_MODELS = gql`
  query GetAvailableModels {
    availableModels
  }
`

interface SettingsListProps {
  items: SystemSetting[]
  categories: string[]
  saveLoading: boolean
  onUpdate: (key: string, value: unknown) => void
}

const SettingsList: React.FC<SettingsListProps> = ({
  items,
  categories,
  saveLoading,
  onUpdate,
}) => {
  const [localValues, setLocalValues] = useState<Record<string, unknown>>(() => {
    const values: Record<string, unknown> = {}
    items.forEach(item => {
      values[item.key] = item.value
    })
    return values
  })
  const [modelOptions, setModelOptions] = useState<{ value: string; label: string }[]>([])

  // Sync local values with items when items change
  useEffect(() => {
    const values: Record<string, unknown> = {}
    items.forEach(item => {
      values[item.key] = item.value
    })
    // Schedule state update to avoid cascading renders
    const timer = setTimeout(() => setLocalValues(values), 0)
    return () => clearTimeout(timer)
  }, [items])

  // Fetch models
  useEffect(() => {
    const fetchModels = async () => {
      const knownLabels: Record<string, string> = {
        'rdd_model.pt': 'RDD Specializált Modell',
      }

      try {
        const { data } = await client.query<{ availableModels: string[] }>({
          query: GET_AVAILABLE_MODELS,
          fetchPolicy: 'network-only',
        })

        if (data?.availableModels) {
          const options = data.availableModels
            .map((m: string) => {
              const filename = m.split('/').pop() || m
              if (knownLabels[filename]) return { value: m, label: knownLabels[filename] }

              // DYNAMIC LABEL GENERATION
              let label = filename.replace('.pt', '')
              const isBest = label.includes('best')
              const isSeg = label.includes('seg')

              // Extract version and size
              const verMatch = label.match(/yolo(v?\d+)([nsmlx])?/i)
              let info = ''
              if (verMatch) {
                const ver = verMatch[1].toLowerCase().replace('v', '')
                const size = verMatch[2] ? verMatch[2].toUpperCase() : ''
                const sizeNames: Record<string, string> = {
                  N: 'Nano',
                  S: 'Kicsi',
                  M: 'Közepes',
                  L: 'Nagy',
                  X: 'Extra',
                }
                info = `YOLOv${ver}${size ? '-' + size : ''}${size ? ' (' + sizeNames[size] + ')' : ''}`
              }

              if (isBest) {
                label = `🎯 Saját Tanított ${info || label.replace('-best', '')} (Legjobb)`
              } else if (info) {
                label = `${info}${isSeg ? ' Szegmentáló' : ''}`
              }

              // General check for timestamp suffix (e.g. ...-20260104.pt)
              const dateMatch = filename.match(/[-_](\d{8})(?:[-_](\d{4,6}))?\.pt$/)
              if (dateMatch) {
                const dStr = dateMatch[1] // 20260104
                const tStr = dateMatch[2] // HHMM or HHMMSS

                const y = dStr.slice(0, 4)
                const m = dStr.slice(4, 6)
                const d = dStr.slice(6, 8)

                let timeDisplay = ''
                if (tStr && tStr.length >= 4) {
                  timeDisplay = ` ${tStr.slice(0, 2)}:${tStr.slice(2, 4)}`
                }

                // Append to whatever label we built above
                label += ` (${y}-${m}-${d}${timeDisplay})`
              } else if (filename.startsWith('model_') && !label.includes('Mentett')) {
                // Fallback for old 'model_YYYYMMDD' format if regex didn't catch it or if it didn't match the suffix pattern perfectly
                // (Though the regex usually catches it if it ends in .pt)
                const datePart = filename.replace('model_', '').replace('.pt', '')
                if (datePart.length >= 8 && /^\d+$/.test(datePart)) {
                  label = `Mentett Modell (${datePart.slice(0, 4)}-${datePart.slice(4, 6)}-${datePart.slice(6, 8)})`
                }
              }

              return { value: m, label }
            })
            // Sort: Known models and "Best" models first
            .sort((a, b) => {
              const aIsBest = a.label.includes('🎯')
              const bIsBest = b.label.includes('🎯')
              if (aIsBest && !bIsBest) return -1
              if (!aIsBest && bIsBest) return 1
              return a.label.localeCompare(b.label)
            })

          setModelOptions(options)
        } else {
          setModelOptions([])
        }
      } catch (err) {
        console.error('Failed to fetch models:', err)
        setModelOptions([])
      }
    }

    fetchModels()
  }, [])

  const handleLocalUpdate = (key: string, value: unknown) => {
    setLocalValues(prev => ({ ...prev, [key]: value }))
    onUpdate(key, value)
  }

  const getIcon = (category: string) => {
    switch (category) {
      case 'AI & Modell':
        return <BrainCircuit size={18} />
      case 'Súlyok':
        return <BarChart3 size={18} />
      case 'Google Street View':
        return <MapIcon size={18} />
      case 'Tanítás':
        return <Wand2 size={18} />
      default:
        return <Settings size={18} />
    }
  }

  const categoryColors: Record<string, string> = {
    'AI & Modell': '#a78bfa',
    'Súlyok': '#34d399',
    'Google Street View': '#fbbf24',
    'Tanítás': '#60a5fa',
    'Egyéb': '#9ca3af',
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '64px' }}>
      {categories.map(category => (
        <section key={category}>
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '12px',
              marginBottom: '32px',
            }}>
            <div
              style={{
                color: categoryColors[category] || '#9ca3af',
                padding: '8px',
                borderRadius: '10px',
                background: 'rgba(255,255,255,0.03)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
              }}>
              {getIcon(category)}
            </div>
            <h2
              style={{
                textTransform: 'uppercase',
                letterSpacing: '0.1em',
                fontSize: '0.9rem',
                fontWeight: 700,
                color: '#f3f4f6',
              }}>
              {category}
            </h2>
            <div
              style={{
                flex: 1,
                height: '1px',
                background: 'linear-gradient(90deg, rgba(255,255,255,0.1), transparent)',
                marginLeft: '12px',
              }}
            />
          </div>

          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fill, minmax(340px, 1fr))',
              gap: '24px',
            }}>
            {items
              .filter(item => (item.category || 'Egyéb') === category)
              .map(item => (
                <GlassPanel
                  key={item.key}
                  title={item.description || item.key}
                  description={item.explanation}
                  secondaryText={item.key}
                  style={{
                    padding: '24px',
                    display: 'flex',
                    flexDirection: 'column',
                    gap: '16px',
                    transition: 'transform 0.2s cubic-bezier(0.4, 0, 0.2, 1)',
                    cursor: 'default',
                    height: '100%',
                    borderWidth: '1px',
                    borderStyle: 'solid',
                    borderColor: 'rgba(255,255,255,0.05)',
                  }}
                  className="hover-lift">
                  <FormControl>
                    <div style={{ display: 'flex', gap: '12px', alignItems: 'center' }}>
                      <div
                        style={{
                          flex: 1,
                          maxWidth: typeof item.value === 'string' ? '400px' : '150px',
                        }}>
                        {item.key === 'ai_model' || item.key === 'cleaner_model' ? (
                          <Select
                            value={String(localValues[item.key] ?? '')}
                            options={modelOptions}
                            onChange={val => handleLocalUpdate(item.key, val)}
                          />
                        ) : item.key === 'training_provider' ? (
                          <Select
                            value={String(localValues[item.key] ?? 'local')}
                            options={[
                              { value: 'local', label: '💻 Lokális (Saját Gép)' },
                              { value: 'google_colab', label: '☁️ Google Colab (Felhő)' },
                            ]}
                            onChange={val => handleLocalUpdate(item.key, val)}
                          />
                        ) : typeof item.value === 'string' ? (
                          <TextInput
                            value={String(localValues[item.key] ?? '')}
                            onChange={val => setLocalValues(prev => ({ ...prev, [item.key]: val }))}
                            onBlur={(e: React.FocusEvent<HTMLInputElement>) =>
                              handleLocalUpdate(item.key, e.target.value)
                            }
                            placeholder="Érték..."
                          />
                        ) : (
                          <NumberInput
                            value={Number(localValues[item.key] ?? 0)}
                            onChange={(val: string | number) =>
                              setLocalValues(prev => ({ ...prev, [item.key]: val }))
                            }
                            onBlur={(e: React.FocusEvent<HTMLInputElement>) =>
                              handleLocalUpdate(item.key, parseFloat(e.target.value))
                            }
                          />
                        )}
                      </div>

                      {saveLoading &&
                        localValues[item.key] !== items.find(i => i.key === item.key)?.value && (
                          <div style={{ display: 'flex', alignItems: 'center' }}>
                            <Loader2 className="animate-spin" size={18} color="#3b82f6" />
                          </div>
                        )}
                    </div>
                  </FormControl>
                </GlassPanel>
              ))}
          </div>
        </section>
      ))}
    </div>
  )
}

export default SettingsList
