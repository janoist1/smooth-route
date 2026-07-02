import React, { useState } from 'react'
import { CheckCircle, AlertTriangle, Download, FileText, RefreshCw, Cpu, Play } from 'lucide-react'
import { ProgressBar } from '../../ui'
import type { TrainingState } from '../types'
import { AnalysisHubLayout } from './AnalysisHubLayout'

interface DinoTrainingPanelProps {
  trainingStatus: TrainingState['trainingStatus']
  analysisStatus: string
  analysisMessage: string | null
  analysisProgress: number
  analysisTotal: number
  analysisJobId: string | null
  exports: TrainingState['exports']
  onStartTraining: () => void
  onRunAnalysis: (reanalyze: boolean) => void
  onStopJob: (jobId: string) => void
  onResetJob: () => void
}

export const DinoTrainingPanel: React.FC<DinoTrainingPanelProps> = ({
  trainingStatus,
  analysisStatus,
  analysisMessage,
  analysisProgress,
  analysisTotal,
  analysisJobId,
  exports,
  onStartTraining,
  onRunAnalysis,
  onStopJob,
  onResetJob
}) => {
  const [reanalyze, setReanalyze] = useState(false)

  const statusBadge = (
    <div
      style={{
        fontSize: '0.75rem',
        fontWeight: 'bold',
        color: '#4ade80',
        background: 'rgba(74, 222, 128, 0.1)',
        padding: '2px 8px',
        borderRadius: '6px',
        border: '1px solid rgba(74, 222, 128, 0.2)',
      }}>
      READY
    </div>
  )

  const configContent = (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
      <div style={{ fontSize: '0.9rem', color: '#d1d5db', lineHeight: '1.5' }}>
        Training will export all leveled data (1-5) and fine-tune a classification head on top of the frozen DINOv2 backbone.
      </div>

       <div style={{ display: 'flex', alignItems: 'center' }}>
        <label
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '12px',
            cursor: 'pointer',
            padding: '8px 12px',
            borderRadius: '8px',
            width: '100%',
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
  )

  const isRunning = trainingStatus === 'running' || trainingStatus === 'starting' || analysisStatus === 'running' || analysisStatus === 'starting'

  const actionsContent = (
    <>
      <button
        onClick={() => onRunAnalysis(reanalyze)}
        disabled={isRunning}
        style={{
          flex: '1',
          padding: '12px',
          borderRadius: '10px',
          background: isRunning ? '#374151' : 'linear-gradient(135deg, #3b82f6, #2563eb)',
          color: 'white',
          fontWeight: 600,
          border: 'none',
          cursor: isRunning ? 'not-allowed' : 'pointer',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          gap: '8px',
          boxShadow: isRunning ? 'none' : '0 4px 12px rgba(59, 130, 246, 0.3)',
          transition: 'all 0.2s',
        }}>
        <Play size={16} />
        <span>Run Analysis</span>
      </button>

      <button
        onClick={onStartTraining}
        disabled={isRunning}
        style={{
          flex: '1',
          padding: '12px',
          borderRadius: '10px',
          background: isRunning ? '#374151' : 'linear-gradient(135deg, #10b981, #059669)',
          color: 'white',
          fontWeight: 600,
          border: 'none',
          cursor: isRunning ? 'not-allowed' : 'pointer',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          gap: '8px',
          boxShadow: isRunning ? 'none' : '0 4px 12px rgba(16, 185, 129, 0.3)',
          transition: 'all 0.2s',
        }}>
        <RefreshCw size={16} />
        <span>Start Training</span>
      </button>
      
      {isRunning && (
        <button
          onClick={() => analysisJobId && onStopJob(analysisJobId)}
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
          title="Stop Job">
          <RefreshCw size={16} style={{ color: '#f87171' }} />
        </button>
      )}
    </>
  )

  const statusContent = (
    <>
      {trainingStatus !== 'running' && trainingStatus !== 'starting' && analysisStatus !== 'completed' && analysisStatus !== 'failed' && (
        <div style={{ color: '#9ca3af', fontSize: '0.9rem', lineHeight: 1.5 }}>
          Model ready: <span style={{ color: 'white', fontWeight: 600 }}>DINOv2 (Frozen) + MLP Head</span>
          <br />
          Ready to start training.
        </div>
      )}

      {(trainingStatus === 'running' || trainingStatus === 'starting') && (
        <div style={{ marginTop: '0' }}>
          <ProgressBar
            progress={analysisProgress}
            total={analysisTotal > 0 ? analysisTotal : 100}
            label="" 
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
              <span>{analysisMessage || 'Training...'}</span>
            </div>
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
              Training Complete
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
                background: 'rgba(59, 130, 246, 0.1)',
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
                    Download Artifacts
                </span>
              </div>

              <div style={{ display: 'flex', gap: '8px' }}>
                {exports.notebookPath && (
                    <a
                      href={exports.notebookPath}
                      download
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
                      Notebook
                    </a>
                )}
                {exports.datasetPath && (
                    <a
                      href={exports.datasetPath}
                      download
                      style={{
                        flex: 1,
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        gap: '8px',
                        padding: '12px',
                        background: '#059669',
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
                      Dataset
                    </a>
                )}
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
          <span style={{ fontSize: '0.85rem', fontWeight: 500 }}>{analysisMessage || 'An error occurred'}</span>
        </div>
      )}
    </>
  )

  return (
    <AnalysisHubLayout
      title="DINO Classification Hub"
      statusBadge={statusBadge}
      configContent={configContent}
      actionsContent={actionsContent}
      statusContent={statusContent}
    />
  )
}
