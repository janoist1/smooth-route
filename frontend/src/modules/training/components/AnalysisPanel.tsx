import React, { useState } from 'react'
import { Play, RefreshCw, Cpu, CheckCircle, AlertTriangle, Download, FileText } from 'lucide-react'
import { GlassPanel, ProgressBar } from '../../ui'

interface AnalysisPanelProps {
  analysisStatus: string
  analysisMessage: string | null
  analysisProgress: number
  analysisTotal: number
  trainingStatus: string
  pendingAnalysisCount: number
  onRunAnalysis: (params: { strategy: string; limit: number; reanalyze: boolean }) => void
  onStartTraining: () => void
  onStopJob: () => void
  onResetJob: () => void
  modelName?: string
  exports?: {
    notebookPath?: string
    datasetPath?: string
    instructions?: string
  } | null
}

const AnalysisPanel: React.FC<AnalysisPanelProps> = ({
  analysisStatus,
  analysisMessage,
  analysisProgress,
  analysisTotal,
  trainingStatus,
  pendingAnalysisCount,
  onRunAnalysis,
  onStartTraining,
  onStopJob,
  onResetJob,
  modelName = 'YOLOv8',
  exports,
}) => {
  const [limit, setLimit] = useState(0)
  const [reanalyze, setReanalyze] = useState(false)

  const isRunning =
    (analysisStatus === 'running' || trainingStatus === 'running') && analysisStatus !== 'completed'

  // Clean up message from manual percentage suffix
  const cleanMessage = analysisMessage?.replace(/\s\d+%\s*$/, '') || ''

  return (
    <GlassPanel style={{ marginBottom: '40px' }}>
      <div
        style={{
          marginBottom: '24px',
          display: 'flex',
          alignItems: 'center',
          gap: '12px',
          paddingBottom: '20px',
          borderBottom: '1px solid rgba(255, 255, 255, 0.05)',
        }}>
        <div
          style={{
            width: '32px',
            height: '32px',
            borderRadius: '8px',
            background: 'linear-gradient(135deg, #3b82f6, #8b5cf6)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            boxShadow: '0 4px 12px rgba(59, 130, 246, 0.3)',
          }}>
          <Cpu size={18} color="white" />
        </div>
        <div>
          <h2 style={{ fontSize: '1.1rem', fontWeight: 'bold' }}>AI Analysis Hub</h2>
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '32px' }}>
        {/* Left: Controls */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
          <div>
            <label
              style={{
                display: 'block',
                fontSize: '0.85rem',
                fontWeight: 600,
                color: '#9ca3af',
                marginBottom: '8px',
                textTransform: 'uppercase',
                letterSpacing: '0.05em',
              }}>
              Configuration
            </label>
            <div
              style={{
                display: 'grid',
                gridTemplateColumns: '1fr 1fr',
                gap: '16px',
                background: 'rgba(255,255,255,0.02)',
                padding: '16px',
                borderRadius: '12px',
                border: '1px solid rgba(255,255,255,0.05)',
              }}>
              <div>
                <label
                  style={{
                    display: 'block',
                    fontSize: '0.8rem',
                    color: '#d1d5db',
                    marginBottom: '6px',
                  }}>
                  Batch Limit
                </label>
                <div style={{ position: 'relative' }}>
                  <input
                    type="number"
                    value={limit}
                    onChange={e => setLimit(Number(e.target.value))}
                    style={{
                      width: '100%',
                      background: '#111827',
                      border: '1px solid rgba(255,255,255,0.1)',
                      padding: '8px 12px',
                      borderRadius: '8px',
                      color: 'white',
                      fontSize: '0.9rem',
                    }}
                    min={0}
                    step={10}
                  />
                  <div
                    style={{
                      position: 'absolute',
                      right: '12px',
                      top: '50%',
                      transform: 'translateY(-50%)',
                      fontSize: '0.75rem',
                      color: '#6b7280',
                    }}>
                    0 = Unlimited
                  </div>
                </div>
              </div>

              <div style={{ display: 'flex', alignItems: 'flex-end' }}>
                <label
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: '12px',
                    cursor: 'pointer',
                    padding: '8px 12px',
                    borderRadius: '8px',
                    width: '100%',
                    height: '38px', // Match input height
                    background: 'rgba(255,255,255,0.03)',
                    border: '1px solid rgba(255,255,255,0.05)',
                    transition: 'all 0.2s',
                  }}
                  className="hover:bg-white/5">
                  <input
                    type="checkbox"
                    checked={reanalyze}
                    onChange={e => setReanalyze(e.target.checked)}
                    style={{
                      width: '16px',
                      height: '16px',
                      accentColor: '#3b82f6',
                    }}
                  />
                  <span style={{ fontSize: '0.85rem', color: '#d1d5db' }}>Force Re-analysis</span>
                </label>
              </div>
            </div>
          </div>

          <div style={{ display: 'flex', gap: '12px' }}>
            <button
              onClick={() => onRunAnalysis({ strategy: 'YOLO', limit, reanalyze })}
              disabled={isRunning}
              style={{
                flex: '2',
                padding: '12px',
                borderRadius: '10px',
                background: isRunning ? '#374151' : 'linear-gradient(135deg, #2563eb, #1d4ed8)',
                color: 'white',
                fontWeight: 600,
                border: 'none',
                cursor: isRunning ? 'not-allowed' : 'pointer',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                gap: '8px',
                boxShadow: isRunning ? 'none' : '0 4px 12px rgba(37, 99, 235, 0.2)',
                transition: 'all 0.2s',
              }}>
              <Play size={16} fill="white" />
              <span>Run Analysis</span>
            </button>
            <button
              onClick={onStartTraining}
              disabled={isRunning}
              style={{
                flex: '1',
                padding: '12px',
                borderRadius: '10px',
                background: 'rgba(16, 185, 129, 0.1)',
                color: '#10b981',
                fontWeight: 600,
                border: '1px solid rgba(16, 185, 129, 0.2)',
                cursor: isRunning ? 'not-allowed' : 'pointer',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                gap: '8px',
                transition: 'all 0.2s',
              }}>
              <RefreshCw size={16} />
              <span>Fine-tune</span>
            </button>
            {isRunning && (
              <button
                onClick={onStopJob}
                style={{
                  padding: '12px',
                  width: '46px',
                  borderRadius: '10px',
                  background: 'rgba(239, 68, 68, 0.1)',
                  color: '#f87171',
                  border: '1px solid rgba(239, 68, 68, 0.2)',
                  cursor: 'pointer',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                }}
                title="Stop Analysis">
                <RefreshCw size={16} style={{ color: '#f87171' }} />
              </button>
            )}
          </div>
        </div>

        {/* Right: Status */}
        <div style={{ display: 'flex', flexDirection: 'column' }}>
          <div
            style={{
              flex: 1,
              background: 'rgba(0,0,0,0.2)',
              borderRadius: '12px',
              padding: '16px',
              border: '1px solid rgba(255,255,255,0.05)',
              display: 'flex',
              flexDirection: 'column',
            }}>
            <div
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                marginBottom: '16px',
                alignItems: 'flex-start',
              }}>
              <span
                style={{
                  fontSize: '0.75rem',
                  fontWeight: 'bold',
                  textTransform: 'uppercase',
                  letterSpacing: '0.05em',
                  color: '#60a5fa',
                }}>
                System Status
              </span>
              <div
                style={{
                  fontSize: '0.75rem',
                  fontWeight: 'bold',
                  color: pendingAnalysisCount > 0 ? '#fb923c' : '#4ade80',
                  background:
                    pendingAnalysisCount > 0
                      ? 'rgba(251, 146, 60, 0.1)'
                      : 'rgba(74, 222, 128, 0.1)',
                  padding: '2px 8px',
                  borderRadius: '6px',
                  border: `1px solid ${pendingAnalysisCount > 0 ? 'rgba(251, 146, 60, 0.2)' : 'rgba(74, 222, 128, 0.2)'}`,
                }}>
                {pendingAnalysisCount} PENDING
              </div>
            </div>

            <div
              style={{
                flex: 1,
                display: 'flex',
                flexDirection: 'column',
                justifyContent: 'center',
              }}>
              {!isRunning && analysisStatus !== 'completed' && analysisStatus !== 'failed' && (
                <div style={{ color: '#9ca3af', fontSize: '0.9rem', lineHeight: 1.5 }}>
                  Model ready: <span style={{ color: 'white', fontWeight: 600 }}>{modelName}</span>
                  <br />
                  Ready to process or train.
                </div>
              )}

              {isRunning && (
                <div style={{ marginTop: '0' }}>
                  <ProgressBar
                    progress={analysisProgress}
                    total={analysisTotal > 0 ? analysisTotal : 1}
                    label="" // Hide default label inside bar for cleaner look
                  />
                  <div
                    style={{
                      marginTop: '8px',
                      fontSize: '0.85rem',
                      fontFamily: 'monospace',
                      color: '#60a5fa',
                      display: 'flex',
                      justifyContent: 'space-between',
                    }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                      <Cpu size={14} className="animate-pulse" />
                      <span>{cleanMessage}</span>
                    </div>
                    <span style={{ fontWeight: 'bold' }}>
                      {Math.round(
                        (analysisProgress / (analysisTotal > 0 ? analysisTotal : 1)) * 100,
                      )}
                      %
                    </span>
                  </div>
                </div>
              )}

              {analysisStatus === 'completed' && (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                  <div
                    style={{
                      padding: '12px',
                      background: 'rgba(34, 197, 94, 0.1)',
                      border: '1px solid rgba(34, 197, 94, 0.2)',
                      borderRadius: '8px',
                      display: 'flex',
                      alignItems: 'center',
                      gap: '8px',
                      color: '#4ade80',
                    }}>
                    <CheckCircle size={16} />
                    <span style={{ fontSize: '0.85rem', fontWeight: 500 }}>
                      {exports ? 'Exportálás Sikeres' : 'Analysis Complete'}
                    </span>
                    <button
                      onClick={onResetJob}
                      style={{
                        marginLeft: 'auto',
                        background: 'none',
                        border: 'none',
                        color: 'currentColor',
                        opacity: 0.8,
                        cursor: 'pointer',
                        fontSize: '0.75rem',
                        fontWeight: 600,
                      }}>
                      DISMISS
                    </button>
                  </div>

                  {exports && (
                    <div
                      style={{
                        background: 'rgba(59, 130, 246, 0.1)', // More visible blue background
                        border: '1px solid rgba(59, 130, 246, 0.3)',
                        borderRadius: '10px',
                        padding: '16px',
                        display: 'flex',
                        flexDirection: 'column',
                        gap: '12px',
                        marginTop: '8px',
                      }}>
                      <div
                        style={{
                          display: 'flex',
                          alignItems: 'center',
                          gap: '8px',
                          color: '#60a5fa',
                        }}>
                        <Download size={18} />
                        <span style={{ fontSize: '0.9rem', fontWeight: 700 }}>
                          Exportált Fájlok Letöltése
                        </span>
                      </div>

                      <div style={{ fontSize: '0.85rem', color: '#cbd5e1', lineHeight: 1.4 }}>
                        A tanításhoz szükséges fájlok elkészültek. Töltsd le őket az alábbi
                        gombokkal:
                      </div>

                      <div style={{ display: 'flex', gap: '8px' }}>
                        <a
                          href={exports.notebookPath || '#'}
                          download={exports.notebookPath?.split('/').pop() || 'notebook.ipynb'}
                          style={{
                            flex: 1,
                            display: 'flex',
                            alignItems: 'center',
                            justifyContent: 'center',
                            gap: '8px',
                            padding: '12px',
                            background: '#2563eb',
                            color: 'white',
                            borderRadius: '8px',
                            fontSize: '0.85rem',
                            fontWeight: 600,
                            textDecoration: 'none',
                            transition: 'all 0.2s',
                            boxShadow: '0 2px 4px rgba(0,0,0,0.2)',
                          }}
                          className="hover:bg-blue-600">
                          <FileText size={16} />
                          Notebook Letöltése
                        </a>
                        <a
                          href={exports.datasetPath || '#'}
                          download={exports.datasetPath?.split('/').pop() || 'dataset.zip'}
                          style={{
                            flex: 1,
                            display: 'flex',
                            alignItems: 'center',
                            justifyContent: 'center',
                            gap: '8px',
                            padding: '12px',
                            background: '#059669', // Green for dataset
                            color: 'white',
                            borderRadius: '8px',
                            fontSize: '0.85rem',
                            fontWeight: 600,
                            textDecoration: 'none',
                            transition: 'all 0.2s',
                            boxShadow: '0 2px 4px rgba(0,0,0,0.2)',
                          }}
                          className="hover:bg-emerald-600">
                          <Download size={16} />
                          Dataset (.zip)
                        </a>
                      </div>
                    </div>
                  )}
                </div>
              )}

              {analysisStatus === 'failed' && (
                <div
                  style={{
                    padding: '10px',
                    background: 'rgba(239, 68, 68, 0.1)',
                    border: '1px solid rgba(239, 68, 68, 0.2)',
                    borderRadius: '8px',
                    display: 'flex',
                    alignItems: 'center',
                    gap: '8px',
                    color: '#f87171',
                  }}>
                  <AlertTriangle size={16} />
                  <span style={{ fontSize: '0.85rem', fontWeight: 500 }}>{analysisMessage}</span>
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    </GlassPanel>
  )
}

export default AnalysisPanel
