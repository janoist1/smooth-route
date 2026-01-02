import React, { useState } from 'react'
import {
  Play,
  RefreshCw,
  Cpu,
  Layers,
  Zap,
  CheckCircle,
  AlertTriangle
} from 'lucide-react'
import { GlassPanel, SelectionButton, ProgressBar } from '../../ui'

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
  onResetJob
}) => {
  const [strategy, setStrategy] = useState('HEURISTIC')
  const [limit, setLimit] = useState(0)
  const [reanalyze, setReanalyze] = useState(false)

  const isRunning = analysisStatus === 'running' || trainingStatus === 'running'

  return (
    <GlassPanel style={{ marginBottom: '40px' }}>
      <div style={{ paddingBottom: '24px', borderBottom: '1px solid rgba(255, 255, 255, 0.05)', display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '24px' }}>
        <div style={{ width: '40px', height: '40px', borderRadius: '12px', background: 'linear-gradient(135deg, #3b82f6, #8b5cf6)', display: 'flex', alignItems: 'center', justifyContent: 'center', boxShadow: '0 4px 12px rgba(59, 130, 246, 0.3)' }}>
          <Cpu size={20} color="white" />
        </div>
        <div>
          <h2 style={{ fontSize: '1.25rem', fontWeight: 'bold' }}>AI Analysis Hub</h2>
          <div style={{ fontSize: '0.875rem', color: '#9ca3af' }}>Configure automated road quality assessment</div>
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr', gap: '32px' }}>
        {/* Left Column: Configuration */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
          
          {/* Strategy Selection */}
          <div>
            <label style={{ display: 'block', fontSize: '0.875rem', fontWeight: 600, color: '#d1d5db', marginBottom: '12px' }}>Analysis Strategy</label>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
              <SelectionButton
                label="Heuristic"
                subtext="Fast rule-based analysis using sensor data patterns."
                icon={<Layers size={18} />}
                selected={strategy === 'HEURISTIC'}
                onClick={() => setStrategy('HEURISTIC')}
                color="blue"
              />
              
              <SelectionButton
                label="Deep Learning"
                subtext="Advanced visual analysis using fine-tuned models."
                icon={<Zap size={18} />}
                selected={strategy === 'YOLO'}
                onClick={() => setStrategy('YOLO')}
                color="purple"
              />

              <SelectionButton
                label="Fusion"
                subtext="Hybrid mode combining YOLO and heuristic logic."
                icon={<Layers size={18} />}
                selected={strategy === 'FUSION'}
                onClick={() => setStrategy('FUSION')}
                color="purple"
              />
            </div>
          </div>

          {/* Advanced Options */}
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '20px' }}>
            <div>
              <label style={{ display: 'block', fontSize: '0.875rem', fontWeight: 600, color: '#d1d5db', marginBottom: '8px' }}>Batch Limit</label>
              <div style={{ position: 'relative' }}>
                <input 
                  type="number" 
                  value={limit}
                  onChange={(e) => setLimit(Number(e.target.value))}
                  style={{ width: '100%', background: '#111827', border: '1px solid rgba(255,255,255,0.1)', padding: '10px 12px', borderRadius: '8px', color: 'white' }}
                  min={0}
                  step={10}
                />
                <div style={{ position: 'absolute', right: '12px', top: '50%', transform: 'translateY(-50%)', fontSize: '0.75rem', color: '#6b7280' }}>
                  0 = Unlimited
                </div>
              </div>
            </div>

            <div style={{ display: 'flex', alignItems: 'flex-end' }}>
              <label style={{ display: 'flex', alignItems: 'center', gap: '12px', cursor: 'pointer', padding: '10px', borderRadius: '8px', width: '100%', background: 'rgba(255,255,255,0.03)', border: '1px solid rgba(255,255,255,0.05)' }}>
                <input 
                  type="checkbox" 
                  checked={reanalyze}
                  onChange={(e) => setReanalyze(e.target.checked)}
                  style={{ width: '16px', height: '16px' }}
                />
                <span style={{ fontSize: '0.875rem', color: '#d1d5db' }}>Force Re-analysis</span>
              </label>
            </div>
          </div>
        </div>

        {/* Right Column: Information & Actions */}
        <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
          <div style={{ flex: 1, background: 'rgba(0,0,0,0.2)', borderRadius: '12px', padding: '16px', marginBottom: '16px', border: '1px solid rgba(255,255,255,0.05)' }}>
            <div style={{ display: 'flex', gap: '8px', marginBottom: '8px', color: '#60a5fa' }}>
              <span style={{ fontSize: '0.75rem', fontWeight: 'bold', textTransform: 'uppercase', letterSpacing: '0.05em' }}>System Status</span>
            </div>
            <div style={{ fontSize: '0.875rem', color: '#93c5fd', lineHeight: 1.5, display: 'flex', flexDirection: 'column', gap: '8px' }}>
              <span>Ready to process training data. Select a strategy to begin batch analysis or fine-tune the model.</span>
              
              <div style={{ marginTop: '4px', padding: '10px', background: 'rgba(59, 130, 246, 0.1)', borderRadius: '8px', border: '1px solid rgba(59, 130, 246, 0.2)' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <span style={{ color: '#bfdbfe', fontSize: '0.75rem', fontWeight: 600 }}>POINT TO ANALYZE</span>
                  <span style={{ color: 'white', fontWeight: 'bold' }}>{pendingAnalysisCount}</span>
                </div>
                {pendingAnalysisCount === 0 && (
                  <div style={{ fontSize: '0.7rem', color: '#fb923c', marginTop: '6px', display: 'flex', alignItems: 'center', gap: '4px' }}>
                    <AlertTriangle size={12} />
                    <span>All points analyzed. Use <b>Force Re-analysis</b> to restart.</span>
                  </div>
                )}
              </div>
            </div>
          </div>

          <div style={{ display: 'flex', gap: '12px' }}>
            <button 
              onClick={() => onRunAnalysis({ strategy, limit, reanalyze })}
              disabled={isRunning}
              style={{
                flex: '2',
                padding: '14px',
                borderRadius: '12px',
                background: isRunning ? '#374151' : 'linear-gradient(135deg, #2563eb, #1d4ed8)',
                color: 'white',
                fontWeight: 'bold',
                border: 'none',
                cursor: isRunning ? 'not-allowed' : 'pointer',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                gap: '8px',
                boxShadow: '0 4px 12px rgba(37, 99, 235, 0.3)'
              }}
            >
              <Play size={18} fill="white" />
              Run Analysis
            </button>
            <button 
              onClick={onStartTraining}
              disabled={isRunning}
              style={{
                flex: '1',
                padding: '14px',
                borderRadius: '12px',
                background: 'rgba(16, 185, 129, 0.1)',
                color: '#10b981',
                fontWeight: 'bold',
                border: '1px solid rgba(16, 185, 129, 0.3)',
                cursor: isRunning ? 'not-allowed' : 'pointer',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                gap: '8px'
              }}
            >
              <RefreshCw size={18} />
              Fine-tune
            </button>
            {isRunning && (
              <button 
                onClick={onStopJob}
                style={{
                  padding: '14px',
                  width: '50px',
                  borderRadius: '12px',
                  background: 'rgba(239, 68, 68, 0.1)',
                  color: '#f87171',
                  fontWeight: 'bold',
                  border: '1px solid rgba(239, 68, 68, 0.3)',
                  cursor: 'pointer',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center'
                }}
                title="Stop Analysis"
              >
                <RefreshCw size={18} style={{ color: '#f87171' }} />
              </button>
            )}
          </div>

          {/* Progress / Status Area - Stable Height to prevent jitter */}
          <div style={{ minHeight: '80px', display: 'flex', flexDirection: 'column', justifyContent: 'center' }}>
            {isRunning && (
              <div style={{ marginTop: '20px' }}>
                <ProgressBar 
                   progress={analysisProgress}
                   total={analysisTotal > 0 ? analysisTotal : 1}
                   label={analysisMessage || 'Inicializálás...'}
                />
              </div>
            )}

            {analysisStatus === 'completed' && (
              <div style={{ marginTop: '20px', padding: '12px', background: 'rgba(34, 197, 94, 0.1)', border: '1px solid rgba(34, 197, 94, 0.2)', borderRadius: '12px', display: 'flex', alignItems: 'center', gap: '8px', color: '#4ade80' }}>
                 <CheckCircle size={18} />
                 <span style={{ fontSize: '0.875rem', fontWeight: 500 }}>Sikeresen befejezve! Frissítsd a listát.</span>
                 <button onClick={onResetJob} style={{ marginLeft: 'auto', background: 'none', border: 'none', color: '#9ca3af', cursor: 'pointer', fontSize: '0.75rem' }}>Bezárás</button>
              </div>
            )}

            {analysisStatus === 'failed' && (
              <div style={{ marginTop: '20px', padding: '12px', background: 'rgba(239, 68, 68, 0.1)', border: '1px solid rgba(239, 68, 68, 0.2)', borderRadius: '12px', display: 'flex', alignItems: 'center', gap: '8px', color: '#f87171' }}>
                 <AlertTriangle size={18} />
                 <span style={{ fontSize: '0.875rem', fontWeight: 500 }}>{analysisMessage}</span>
              </div>
            )}
            
            {(analysisStatus === 'cancelled' ) && (
              <div style={{ marginTop: '20px', padding: '12px', background: 'rgba(107, 114, 128, 0.1)', border: '1px solid rgba(107, 114, 128, 0.2)', borderRadius: '12px', color: '#9ca3af', fontSize: '0.875rem' }}>
                Folyamat leállítva.
              </div>
            )}
          </div>
        </div>
      </div>
    </GlassPanel>
  )
}

export default AnalysisPanel
