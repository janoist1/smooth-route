import React from 'react'
import type { DamageLabel } from '../types'
import {
  CircleDashed,
  Cookie,
  CloudFog,
  Activity,
  Save,
  AlertTriangle,
  Disc,
  MinusSquare,
  Spline,
  Trash2,
  Car,
  Edit3,
  Layers,
} from 'lucide-react'

interface ToolbarProps {
  selectedTool: DamageLabel
  setTool: (tool: DamageLabel) => void
  onSave: () => void
  onDelete?: () => void
  onApplyPrevious?: () => void
  onAutoDetect?: () => void
  loading?: boolean
  autoDetectConf?: number
  onConfChange?: (v: number) => void
  autoDetectClasses?: string[]
  onClassesChange?: (classes: string[]) => void
  // Filter Tool Props
  onFilter?: (threshold: number) => void
  filterThreshold?: number
  onFilterThreshChange?: (v: number) => void
}

const TOOLS = [
  {
    id: 'edit',
    label: 'Edit',
    shortcut: 'E',
    icon: <Edit3 size={22} />,
    desc: 'Poligonok szerkesztése (kattints a módosítandó alakzatra).',
  },
  {
    id: 'long_crack',
    label: 'Long. Crack',
    shortcut: 'L',
    icon: <MinusSquare size={22} />,
    desc: 'Repedés az út irányában.',
  },
  {
    id: 'trans_crack',
    label: 'Trans. Crack',
    shortcut: 'T',
    icon: <MinusSquare size={22} style={{ transform: 'rotate(90deg)' }} />,
    desc: 'Repedés az útra merőlegesen.',
  },
  {
    id: 'alligator_crack',
    label: 'Alligator',
    shortcut: 'A',
    icon: <Activity size={22} />,
    desc: 'Pókhálószerű, sűrű repedések (fáradásos hiba).',
  },
  {
    id: 'pothole',
    label: 'Pothole',
    shortcut: 'P',
    icon: <CircleDashed size={22} />,
    desc: 'Aszfalthiány, kátyú.',
  },
  {
    id: 'patch',
    label: 'Patch',
    shortcut: 'B',
    icon: <Cookie size={22} />,
    desc: 'Aszfaltfoltozás (korábbi javítás).',
  },
  {
    id: 'degradation',
    label: 'Degradation',
    shortcut: 'D',
    icon: <Spline size={22} />,
    desc: 'Felületi kopás, pergés.',
  },
  {
    id: 'shadow',
    label: 'Shadow',
    shortcut: 'S',
    icon: <CloudFog size={22} />,
    desc: 'Árnyék (nem hiba, de zavarhatja az AI-t).',
  },
  {
    id: 'manhole',
    shortcut: 'M',
    label: 'Manhole',
    icon: <Disc size={22} />,
    desc: 'Csatornafedél.',
  },
  {
    id: 'marking',
    shortcut: 'K',
    label: 'Marking',
    icon: <AlertTriangle size={22} />,
    desc: 'Útburkolati jel.',
  },
  {
    id: 'ignore',
    shortcut: 'V',
    label: 'Ignore/Vehicle',
    icon: <Car size={22} />,
    desc: 'Zavaró elem (autó, oszlop, kerítés), amit az AI-nak figyelmen kívül kell hagynia.',
  },
]

const Toolbar: React.FC<ToolbarProps> = ({
  selectedTool,
  setTool,
  onSave,
  onDelete,
  onApplyPrevious,
  onAutoDetect,
  loading,
  autoDetectConf = 0.25,
  onConfChange,
  autoDetectClasses = [],
  onClassesChange,
  onFilter,
  filterThreshold = 0.3,
  onFilterThreshChange,
}) => {
  const [hoveredTool, setHoveredTool] = React.useState<string | null>(null)
  const [showConfSlider, setShowConfSlider] = React.useState(false)
  const [showFilterSlider, setShowFilterSlider] = React.useState(false)

  return (
    <div
      style={{
        width: '60px',
        height: '100vh',
        background: '#1a1a1a',
        borderRight: '1px solid #333',
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        paddingTop: '15px',
        gap: '12px',
        zIndex: 100,
        position: 'absolute',
        left: 0,
        top: 0,
      }}>
      {TOOLS.map(tool => (
        <div
          key={tool.id}
          style={{ position: 'relative' }}
          onMouseEnter={() => setHoveredTool(tool.id)}
          onMouseLeave={() => setHoveredTool(null)}>
          <button
            onClick={() => setTool(tool.id as DamageLabel)}
            style={{
              width: '42px',
              height: '42px',
              background: selectedTool === tool.id ? 'rgba(59, 130, 246, 0.2)' : 'transparent',
              color: selectedTool === tool.id ? '#60a5fa' : '#888',
              border:
                selectedTool === tool.id
                  ? '1px solid rgba(59, 130, 246, 0.4)'
                  : '1px solid transparent',
              borderRadius: '8px',
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              transition: 'all 0.15s ease',
            }}>
            {tool.icon}
          </button>

          {/* Custom Fast Tooltip */}
          {hoveredTool === tool.id && (
            <div
              style={{
                position: 'absolute',
                left: '52px',
                top: '50%',
                transform: 'translateY(-50%)',
                background: '#2d3748',
                color: 'white',
                padding: '8px 12px',
                borderRadius: '6px',
                fontSize: '12px',
                whiteSpace: 'nowrap',
                pointerEvents: 'none',
                zIndex: 100,
                boxShadow: '0 4px 12px rgba(0,0,0,0.4)',
                border: '1px solid #4a5568',
                display: 'flex',
                flexDirection: 'column',
                gap: '2px',
              }}>
              <div style={{ fontWeight: 'bold', color: '#60a5fa' }}>
                {tool.label}{' '}
                <span style={{ color: '#a0aec0', marginLeft: '6px' }}>({tool.shortcut})</span>
              </div>
              <div style={{ color: '#cbd5e0', fontSize: '11px' }}>{tool.desc}</div>
              {/* Tooltip Arrow */}
              <div
                style={{
                  position: 'absolute',
                  left: '-6px',
                  top: '50%',
                  transform: 'translateY(-50%)',
                  width: '0',
                  height: '0',
                  borderTop: '6px solid transparent',
                  borderBottom: '6px solid transparent',
                  borderRight: '6px solid #2d3748',
                }}
              />
            </div>
          )}
        </div>
      ))}

      <div
        style={{
          marginTop: 'auto',
          marginBottom: '20px',
          width: '100%',
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          gap: '12px',
        }}>
        {onAutoDetect && (
          <div
            style={{ position: 'relative' }}
            onMouseEnter={() => setShowConfSlider(true)}
            onMouseLeave={() => setShowConfSlider(false)}>
            {/* Horizontal Bridge to prevent closing on gap */}
            {showConfSlider && (
              <div
                style={{
                  position: 'absolute',
                  left: '30px', // Start slightly inside the button
                  top: '-10px', // Extend up/down for safety
                  bottom: '-10px',
                  width: '30px', // Span across to the slider
                  background: 'transparent',
                  zIndex: 900,
                }}
              />
            )}

            <button
              onClick={loading ? undefined : () => onAutoDetect()}
              title={loading ? 'Processing...' : 'AI Auto-Detect (Magic Wand)'}
              style={{
                width: '40px',
                height: '40px',
                background: loading
                  ? 'rgba(251, 191, 36, 0.1)'
                  : 'linear-gradient(135deg, rgba(168, 85, 247, 0.2), rgba(236, 72, 153, 0.2))',
                color: loading ? '#fbbf24' : '#d8b4fe',
                border: loading
                  ? '1px solid rgba(251, 191, 36, 0.3)'
                  : '1px solid rgba(168, 85, 247, 0.4)',
                borderRadius: '8px',
                cursor: loading ? 'not-allowed' : 'pointer',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                transition: 'all 0.2s',
              }}>
              <span style={{ fontSize: '18px' }}>✨</span>
            </button>

            {/* AI Confidence Slider Overlay */}
            {showConfSlider && !loading && (
              <div
                style={{
                  position: 'absolute',
                  left: '52px',
                  top: '50%',
                  transform: 'translateY(-50%)',
                  background: 'rgba(26, 26, 26, 0.95)',
                  backdropFilter: 'blur(12px)',
                  padding: '12px 16px',
                  borderRadius: '12px',
                  border: '1px solid rgba(168, 85, 247, 0.4)',
                  boxShadow: '0 10px 25px -5px rgba(0, 0, 0, 0.5)',
                  display: 'flex',
                  flexDirection: 'column',
                  gap: '8px',
                  width: '180px',
                  zIndex: 1000,
                }}>
                <div
                  style={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'center',
                  }}>
                  <span style={{ fontSize: '11px', fontWeight: 'bold', color: '#a855f7' }}>
                    AI ÉRZÉKENYSÉG
                  </span>
                  <span
                    style={{
                      fontSize: '12px',
                      fontWeight: 'bold',
                      color: '#fff',
                      background: 'rgba(168, 85, 247, 0.3)',
                      padding: '2px 6px',
                      borderRadius: '4px',
                      minWidth: '35px',
                      textAlign: 'center',
                    }}>
                    {Math.round(autoDetectConf * 100)}%
                  </span>
                </div>
                <input
                  type="range"
                  min="0.01"
                  max="0.99"
                  step="0.01"
                  value={autoDetectConf}
                  onChange={e => onConfChange?.(parseFloat(e.target.value))}
                  style={{
                    width: '100%',
                    accentColor: '#a855f7',
                    cursor: 'pointer',
                    height: '4px',
                    borderRadius: '2px',
                    background: '#333',
                  }}
                />
                <div
                  style={{
                    fontSize: '10px',
                    color: '#666',
                    fontStyle: 'italic',
                    marginBottom: '8px',
                  }}>
                  Alacsonyabb = több észlelés, több zaj.
                </div>

                {/* Class Selection Filter */}
                <div style={{ borderTop: '1px solid rgba(255,255,255,0.1)', paddingTop: '8px' }}>
                  <div
                    style={{
                      fontSize: '10px',
                      fontWeight: 'bold',
                      color: '#a855f7',
                      marginBottom: '6px',
                    }}>
                    KERESETT TÍPUSOK
                  </div>
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: '4px' }}>
                    {[
                      { id: 'ignore', label: 'Ignore' },
                      { id: 'pothole', label: 'Pothole' },
                      { id: 'alligator_crack', label: 'Alligator' },
                      { id: 'long_crack', label: 'Long.' },
                      { id: 'trans_crack', label: 'Trans.' },
                      { id: 'patch', label: 'Patch' },
                      { id: 'degradation', label: 'Degradation' },
                    ].map(opt => {
                      const isSelected = autoDetectClasses.includes(opt.id)
                      return (
                        <div
                          key={opt.id}
                          onClick={() => {
                            if (!onClassesChange) return
                            if (isSelected) {
                              onClassesChange(autoDetectClasses.filter(c => c !== opt.id))
                            } else {
                              onClassesChange([...autoDetectClasses, opt.id])
                            }
                          }}
                          style={{
                            fontSize: '10px',
                            padding: '3px 6px',
                            borderRadius: '4px',
                            cursor: 'pointer',
                            background: isSelected
                              ? 'rgba(168, 85, 247, 0.3)'
                              : 'rgba(255,255,255,0.05)',
                            color: isSelected ? '#d8b4fe' : '#888',
                            border: isSelected
                              ? '1px solid rgba(168, 85, 247, 0.4)'
                              : '1px solid transparent',
                            transition: 'all 0.1s',
                          }}>
                          {opt.label}
                        </div>
                      )
                    })}
                  </div>
                  {autoDetectClasses.length === 0 && (
                    <div style={{ fontSize: '9px', color: '#666', marginTop: '4px' }}>
                      (Üres = minden típus)
                    </div>
                  )}
                </div>
                {/* Overlay Arrow */}
                <div
                  style={{
                    position: 'absolute',
                    left: '-6px',
                    top: '50%',
                    transform: 'translateY(-50%)',
                    width: '0',
                    height: '0',
                    borderTop: '6px solid transparent',
                    borderBottom: '6px solid transparent',
                    borderRight: '6px solid rgba(168, 85, 247, 0.4)',
                  }}
                />
              </div>
            )}
          </div>
        )}
        {onApplyPrevious && (
          <button
            onClick={() => onApplyPrevious()}
            title="Apply Previous (Space)"
            style={{
              width: '40px',
              height: '40px',
              background: 'rgba(52, 152, 219, 0.15)',
              color: '#3498db',
              border: '1px solid rgba(52, 152, 219, 0.3)',
              borderRadius: '8px',
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              transition: 'all 0.2s',
            }}>
            <span style={{ fontSize: '18px', fontWeight: 'bold' }}>P</span>
          </button>
        )}
        {onFilter && (
          <div
            style={{ position: 'relative' }}
            onMouseEnter={() => setShowFilterSlider(true)}
            onMouseLeave={() => setShowFilterSlider(false)}>
            {showFilterSlider && (
              <div
                style={{
                  position: 'absolute',
                  left: '30px',
                  top: '-10px',
                  bottom: '-10px',
                  width: '30px',
                  background: 'transparent',
                  zIndex: 900,
                }}
              />
            )}

            <button
              onClick={() => onFilter(filterThreshold)}
              title="Filter Overlaps (NMS)"
              style={{
                width: '40px',
                height: '40px',
                background: 'rgba(56, 189, 248, 0.15)',
                color: '#38bdf8',
                border: '1px solid rgba(56, 189, 248, 0.3)',
                borderRadius: '8px',
                cursor: 'pointer',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                transition: 'all 0.2s',
              }}>
              <Layers size={20} />
            </button>

            {/* Filter Slider Overlay */}
            {showFilterSlider && (
              <div
                style={{
                  position: 'absolute',
                  left: '52px',
                  top: '50%',
                  transform: 'translateY(-50%)',
                  background: 'rgba(26, 26, 26, 0.95)',
                  backdropFilter: 'blur(12px)',
                  padding: '12px 16px',
                  borderRadius: '12px',
                  border: '1px solid rgba(56, 189, 248, 0.4)',
                  boxShadow: '0 10px 25px -5px rgba(0, 0, 0, 0.5)',
                  display: 'flex',
                  flexDirection: 'column',
                  gap: '8px',
                  width: '180px',
                  zIndex: 1000,
                }}>
                <div
                  style={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'center',
                  }}>
                  <span style={{ fontSize: '11px', fontWeight: 'bold', color: '#38bdf8' }}>
                    ÁTFEDÉS SZŰRÉS (IoU)
                  </span>
                  <span
                    style={{
                      fontSize: '12px',
                      fontWeight: 'bold',
                      color: '#fff',
                      background: 'rgba(56, 189, 248, 0.3)',
                      padding: '2px 6px',
                      borderRadius: '4px',
                      minWidth: '35px',
                      textAlign: 'center',
                    }}>
                    {Math.round(filterThreshold * 100)}%
                  </span>
                </div>
                <input
                  type="range"
                  min="0.05"
                  max="1.0"
                  step="0.05"
                  value={filterThreshold}
                  onChange={e => onFilterThreshChange?.(parseFloat(e.target.value))}
                  style={{
                    width: '100%',
                    accentColor: '#38bdf8',
                    cursor: 'pointer',
                    height: '4px',
                    borderRadius: '2px',
                    background: '#333',
                  }}
                />
                <div style={{ fontSize: '10px', color: '#666', fontStyle: 'italic' }}>
                  Kisebb érték = Szigorúbb szűrés
                  <br />
                  (Több elemet töröl)
                </div>

                {/* Overlay Arrow */}
                <div
                  style={{
                    position: 'absolute',
                    left: '-6px',
                    top: '50%',
                    transform: 'translateY(-50%)',
                    width: '0',
                    height: '0',
                    borderTop: '6px solid transparent',
                    borderBottom: '6px solid transparent',
                    borderRight: '6px solid rgba(56, 189, 248, 0.4)',
                  }}
                />
              </div>
            )}
          </div>
        )}

        <button
          onClick={() => onSave()}
          title="Save (Enter)"
          style={{
            width: '40px',
            height: '40px',
            background: 'rgba(46, 204, 113, 0.15)',
            color: '#2ecc71',
            border: '1px solid rgba(46, 204, 113, 0.3)',
            borderRadius: '8px',
            cursor: 'pointer',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            transition: 'all 0.2s',
          }}>
          <Save size={20} />
        </button>

        {onDelete && (
          <button
            onClick={() => onDelete()}
            title="Delete Ground Truth"
            style={{
              width: '40px',
              height: '40px',
              background: 'rgba(231, 76, 60, 0.15)',
              color: '#e74c3c',
              border: '1px solid rgba(231, 76, 60, 0.3)',
              borderRadius: '8px',
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              transition: 'all 0.2s',
            }}>
            <Trash2 size={20} />
          </button>
        )}
      </div>
    </div>
  )
}

export default Toolbar
