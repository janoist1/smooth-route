import React from 'react'
import { ExternalLink, Loader2, RotateCcw } from 'lucide-react'
import { imageSrc } from '../logic'
import type { PairItem, PairResult } from '../types'

interface PairViewProps {
  pair: PairItem | null
  loading: boolean
  exhausted: boolean
  judged: number
  canUndo: boolean
  onJudge: (result: PairResult) => void
  onUndo: () => void
}

const css = `
.pv-grid { display: grid; grid-template-columns: 1fr; gap: 6px; flex: 1; min-height: 0; }
@media (min-width: 700px) { .pv-grid { grid-template-columns: 1fr 1fr; } }
`

const btn = (accent: string): React.CSSProperties => ({
  flex: 1,
  minHeight: 56,
  borderRadius: 12,
  border: `2px solid ${accent}`,
  background: `${accent}26`,
  color: '#fff',
  fontSize: 15,
  fontWeight: 700,
  touchAction: 'manipulation',
  fontFamily: 'inherit',
})

const Side: React.FC<{ label: string; item: PairItem['a'] }> = ({ label, item }) => (
  <div style={{ position: 'relative', background: '#000', borderRadius: 10, overflow: 'hidden', minHeight: 0 }}>
    <img
      src={imageSrc(item.imageUrl)}
      alt={`${label} kép`}
      draggable={false}
      style={{ width: '100%', height: '100%', objectFit: 'contain', display: 'block' }}
    />
    <span
      style={{ position: 'absolute', top: 6, left: 6, background: 'rgba(0,0,0,0.7)', color: '#fff', borderRadius: 6, padding: '2px 10px', fontWeight: 800 }}>
      {label}
    </span>
    <a
      href={item.streetViewUrl}
      target="_blank"
      rel="noreferrer"
      title="Megnyitás a Google Street View-ban"
      style={{ position: 'absolute', top: 6, right: 6, background: 'rgba(0,0,0,0.6)', color: '#e5e7eb', borderRadius: 6, padding: 5, display: 'flex' }}>
      <ExternalLink size={14} />
    </a>
  </div>
)

/** "Which frame shows the worse road?" — relative judgments are more
 * consistent than absolute grades. The model guess is never shown here. */
const PairView: React.FC<PairViewProps> = ({ pair, loading, exhausted, judged, canUndo, onJudge, onUndo }) => (
  <div style={{ flex: 1, minHeight: 0, display: 'flex', flexDirection: 'column', gap: 6, padding: '0 10px' }}>
    <style>{css}</style>
    <div style={{ fontSize: 14, color: '#cbd5e1', display: 'flex', justifyContent: 'space-between' }}>
      <b>Melyik képen rosszabb az út?</b>
      <span style={{ color: '#94a3b8' }}>{judged} döntés</span>
    </div>
    {pair ? (
      <div className="pv-grid">
        <Side label="A" item={pair.a} />
        <Side label="B" item={pair.b} />
      </div>
    ) : (
      <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#94a3b8', gap: 8 }}>
        {loading ? (
          <>
            <Loader2 size={24} /> Párok keresése…
          </>
        ) : exhausted ? (
          'Most nincs több összevethető pár.'
        ) : null}
      </div>
    )}
    <div style={{ display: 'flex', gap: 6 }}>
      <button disabled={!pair} onClick={() => onJudge('A')} style={btn('#ef4444')}>
        A rosszabb
      </button>
      <button disabled={!pair} onClick={() => onJudge('EQUAL')} style={btn('#94a3b8')}>
        Egyformák
      </button>
      <button disabled={!pair} onClick={() => onJudge('B')} style={btn('#ef4444')}>
        B rosszabb
      </button>
    </div>
    <button
      disabled={!canUndo}
      onClick={onUndo}
      style={{ alignSelf: 'center', background: 'none', color: canUndo ? '#cbd5e1' : '#475569', border: 'none', fontSize: 13, display: 'flex', gap: 6, alignItems: 'center', padding: '4px 8px calc(8px + env(safe-area-inset-bottom))' }}>
      <RotateCcw size={14} /> Visszavonás · billentyűk: ← A, ↓ egyformák, → B
    </button>
  </div>
)

export default PairView
