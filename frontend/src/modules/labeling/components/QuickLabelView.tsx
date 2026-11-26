import React, { useEffect, useState } from 'react'
import {
  ArrowLeft,
  BookOpen,
  ExternalLink,
  Eye,
  EyeOff,
  Loader2,
  RotateCcw,
  SkipForward,
  X,
  ZoomIn,
} from 'lucide-react'
import { useQuickLabel } from '../hooks'
import {
  agreement,
  areaLabel,
  imageSrc,
  isOldCapture,
  keyToAction,
  reasonLabel,
  levelOf,
  RATING_KEY_RANGE,
  RATING_LEVELS,
  STRATEGIES,
} from '../logic'
import type { RqiLevel } from 'modules/ui'
import type { LabelExample, QueueItem } from '../types'

interface QuickLabelViewProps {
  onBack: () => void
}

const css = `
.ql-root { height: 100dvh; display: flex; flex-direction: column; background: #0b0d12; color: #e5e7eb;
  user-select: none; -webkit-user-select: none; -webkit-tap-highlight-color: transparent; }
.ql-btn { touch-action: manipulation; font-family: inherit; }
.ql-btn:active:not(:disabled) { transform: scale(0.97); }
.ql-btn:disabled { opacity: 0.35; cursor: default; }
.ql-kbd { display: none; }
@media (hover: hover) and (pointer: fine) { .ql-kbd { display: inline-block; } }
.ql-spin { animation: qlspin 1s linear infinite; }
@keyframes qlspin { 100% { transform: rotate(360deg); } }
.ql-scroll::-webkit-scrollbar { display: none; }
`

const pill = (active: boolean): React.CSSProperties => ({
  padding: '6px 10px',
  borderRadius: 999,
  border: active ? '1px solid rgba(96,165,250,0.7)' : '1px solid rgba(255,255,255,0.12)',
  background: active ? 'rgba(37,99,235,0.85)' : 'rgba(255,255,255,0.06)',
  color: active ? '#fff' : '#cbd5e1',
  fontSize: 13,
  fontWeight: 500,
  whiteSpace: 'nowrap',
  display: 'inline-flex',
  alignItems: 'center',
  gap: 6,
})

// Control rows stay thumb-sized on a desktop monitor too.
const rowWidth: React.CSSProperties = { width: '100%', maxWidth: 760, marginInline: 'auto', boxSizing: 'border-box' }

const chip: React.CSSProperties = {
  padding: '3px 8px',
  borderRadius: 6,
  background: 'rgba(0,0,0,0.6)',
  color: '#e5e7eb',
  fontSize: 12,
  backdropFilter: 'blur(6px)',
}

const Kbd: React.FC<{ children: React.ReactNode }> = ({ children }) => (
  <span
    className="ql-kbd"
    style={{
      fontSize: 10,
      padding: '0 4px',
      border: '1px solid rgba(255,255,255,0.3)',
      borderRadius: 3,
      marginLeft: 4,
      opacity: 0.7,
    }}>
    {children}
  </span>
)

const modelLine = (item: QueueItem): string => {
  if (item.modelRqi == null || item.modelScore == null) return 'Modell: nincs becslés'
  const level = levelOf(item.modelRqi)
  const pBad = item.modelPBad == null ? '' : ` · P(rossz) ${Math.round(item.modelPBad * 100)}%`
  return `Modell: ${level?.label_hu ?? item.modelRqi} (${item.modelScore.toFixed(2)})${pBad}`
}

const Frame: React.FC<{ item: QueueItem; zoom: boolean; reveal: boolean; onToggleZoom: () => void }> = ({
  item,
  zoom,
  reveal,
  onToggleZoom,
}) => (
  <>
    <img
      key={item.id}
      src={imageSrc(item.imageUrl)}
      alt={`Street View kép #${item.id}`}
      onClick={onToggleZoom}
      draggable={false}
      style={{
        width: '100%',
        height: '100%',
        objectFit: 'contain',
        // Zoom on the lower part of the frame, where the road surface is.
        transform: zoom ? 'scale(2)' : 'none',
        transformOrigin: '50% 80%',
        transition: 'transform 0.15s ease-out',
        cursor: zoom ? 'zoom-out' : 'zoom-in',
      }}
    />
    <div style={{ position: 'absolute', top: 8, left: 8, display: 'flex', gap: 6, flexWrap: 'wrap', right: 48 }}>
      <span style={chip}>{reasonLabel(item)}</span>
      {item.reason === 'uncertain' && <span style={chip}>{areaLabel(item.area)}</span>}
      {item.captureDate && (
        <span style={{ ...chip, color: isOldCapture(item.captureDate) ? '#fbbf24' : '#e5e7eb' }}>
          {isOldCapture(item.captureDate) ? `Régi kép · ${item.captureDate}` : item.captureDate}
        </span>
      )}
    </div>
    <a
      href={item.streetViewUrl}
      target="_blank"
      rel="noreferrer"
      title="Megnyitás a Google Street View-ban"
      style={{ ...chip, position: 'absolute', top: 8, right: 8, display: 'flex', padding: 6 }}>
      <ExternalLink size={16} />
    </a>
    {reveal && (
      <div style={{ ...chip, position: 'absolute', bottom: 8, left: 8, fontSize: 13, color: '#93c5fd' }}>
        {modelLine(item)}
      </div>
    )}
    {zoom && (
      <div style={{ ...chip, position: 'absolute', bottom: 8, right: 8 }}>
        <ZoomIn size={12} style={{ verticalAlign: -2 }} /> 2×
      </div>
    )}
  </>
)

const LastResultLine: React.FC<{ last: { item: QueueItem; rqi: number } | null }> = ({ last }) => {
  if (!last) {
    return <span style={{ color: '#64748b' }}>Értékelés után itt látod a modell tippjét.</span>
  }
  const human = levelOf(last.rqi)
  const verdict = agreement(last.rqi, last.item.modelRqi)
  const color = verdict === 'same' ? '#4ade80' : verdict === 'near' ? '#fbbf24' : verdict === 'far' ? '#f87171' : '#94a3b8'
  return (
    <span>
      Előző: <b style={{ color: human?.color }}>{human?.label_hu ?? last.rqi}</b>
      <span style={{ color }}> · {modelLine(last.item)}</span>
    </span>
  )
}

// Name first (that is what the rater decides on), the stored number secondary.
const RateButton: React.FC<{
  level: RqiLevel
  example?: LabelExample
  disabled: boolean
  onRate: (rqi: number) => void
}> = ({ level, example, disabled, onRate }) => (
  <button
    className="ql-btn"
    disabled={disabled}
    onClick={() => onRate(level.value)}
    aria-label={level.label_hu}
    title={`${level.label_hu} (${level.value})`}
    style={{
      position: 'relative',
      display: 'flex',
      flexDirection: 'column',
      alignItems: 'stretch',
      gap: 4,
      padding: 3,
      minHeight: 84,
      borderRadius: 12,
      border: `2px solid ${level.color}`,
      background: `${level.color}26`,
      color: '#fff',
      overflow: 'hidden',
    }}>
    {example ? (
      <img
        src={imageSrc(example.imageUrl)}
        alt=""
        draggable={false}
        style={{ width: '100%', height: 'clamp(34px, 7.5dvh, 84px)', objectFit: 'cover', objectPosition: '50% 85%', borderRadius: 8 }}
      />
    ) : (
      <div style={{ height: 'clamp(34px, 7.5dvh, 84px)' }} />
    )}
    <span
      style={{
        flex: 1,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        fontSize: 'clamp(12px, 3.6vw, 16px)',
        fontWeight: 700,
        lineHeight: 1.1,
        textAlign: 'center',
        overflowWrap: 'anywhere',
      }}>
      {level.label_hu}
    </span>
    <span
      aria-hidden="true"
      style={{ position: 'absolute', top: 5, left: 6, fontSize: 11, fontWeight: 600, color: '#fff', opacity: 0.85, textShadow: '0 0 3px #000' }}>
      {level.value}
    </span>
  </button>
)

const Rubric: React.FC<{ examples: LabelExample[]; onClose: () => void }> = ({ examples, onClose }) => (
  <div
    role="dialog"
    aria-label="Értékelési skála"
    onClick={onClose}
    style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.6)', zIndex: 20, display: 'flex', alignItems: 'flex-end', justifyContent: 'center' }}>
    <div
      onClick={e => e.stopPropagation()}
      style={{
        width: '100%',
        maxWidth: 560,
        maxHeight: '85dvh',
        overflowY: 'auto',
        background: '#111827',
        borderRadius: '16px 16px 0 0',
        padding: '12px 12px calc(12px + env(safe-area-inset-bottom))',
      }}>
      <div style={{ display: 'flex', alignItems: 'center', marginBottom: 8 }}>
        <b style={{ fontSize: 15 }}>Skála – a legjobbtól a legrosszabbig</b>
        <button className="ql-btn" onClick={onClose} aria-label="Bezárás" style={{ marginLeft: 'auto', background: 'none', color: '#cbd5e1', padding: 6 }}>
          <X size={20} />
        </button>
      </div>
      {RATING_LEVELS.map(level => {
        const ex = examples.find(e => e.rqi === level.value)
        return (
          <div key={level.value} style={{ display: 'flex', gap: 10, alignItems: 'center', padding: '6px 0', borderTop: '1px solid rgba(255,255,255,0.06)' }}>
            {ex ? (
              <img src={imageSrc(ex.imageUrl)} alt={`Példa: ${level.label_hu}`} style={{ width: 132, height: 88, objectFit: 'cover', borderRadius: 8, flexShrink: 0 }} />
            ) : (
              <div style={{ width: 132, height: 88, borderRadius: 8, background: '#1f2937', flexShrink: 0 }} />
            )}
            <div>
              <div style={{ fontWeight: 700, color: level.color }}>
                {level.label_hu} <span style={{ color: '#94a3b8', fontWeight: 400, fontSize: 12 }}>({level.value})</span>
              </div>
              <div style={{ fontSize: 13, color: '#cbd5e1' }}>{level.rubric_hu}</div>
            </div>
          </div>
        )
      })}
      <div style={{ fontSize: 12, color: '#94a3b8', marginTop: 8 }}>
        A kép alsó részét (az útfelületet) értékeld. Nem út, takarja egy autó, vagy nem eldönthető? → Kihagyás.
        Billentyűk: a gomb sarkában lévő szám ({RATING_KEY_RANGE}) értékel, → kihagy, ← visszavon, M modell, szóköz nagyít.
      </div>
    </div>
  </div>
)

export const QuickLabelView: React.FC<QuickLabelViewProps> = ({ onBack }) => {
  const q = useQuickLabel()
  const [zoomFor, setZoomFor] = useState<number | null>(null)
  const [rubricOpen, setRubricOpen] = useState(false)
  const current = q.current
  const zoom = current !== null && zoomFor === current.id
  const toggleZoom = () => setZoomFor(zoom || !current ? null : current.id)

  // Desktop keyboard shortcuts.
  const { rate, skip, undo, toggleReveal, canUndo } = q
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const el = e.target as HTMLElement | null
      if (el && (el.tagName === 'INPUT' || el.tagName === 'SELECT' || el.tagName === 'TEXTAREA' || el.isContentEditable)) return
      const action = keyToAction(e.key, e)
      if (!action) return
      e.preventDefault()
      if (action.type === 'rate') rate(action.rqi)
      else if (action.type === 'skip') skip()
      else if (action.type === 'undo') {
        if (canUndo) undo()
      } else if (action.type === 'reveal') toggleReveal()
      else if (action.type === 'zoom') setZoomFor(prev => (current && prev !== current.id ? current.id : null))
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [rate, skip, undo, toggleReveal, canUndo, current])

  const stats = q.stats
  return (
    <div className="ql-root">
      <style>{css}</style>

      <header style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '8px 12px 4px' }}>
        <button className="ql-btn" onClick={onBack} aria-label="Vissza" style={{ background: 'none', color: '#cbd5e1', padding: 4, display: 'flex' }}>
          <ArrowLeft size={22} />
        </button>
        <b style={{ fontSize: 16, whiteSpace: 'nowrap' }}>Gyors címkézés</b>
        <button
          className="ql-btn"
          onClick={() => setRubricOpen(true)}
          aria-label="Skála és példák"
          title="Skála és példák"
          style={{ background: 'none', color: '#93c5fd', padding: 4, display: 'flex' }}>
          <BookOpen size={20} />
        </button>
        <div style={{ marginLeft: 'auto', fontSize: 12, color: '#94a3b8', textAlign: 'right', lineHeight: 1.25 }} aria-live="polite">
          <div>
            <b style={{ color: '#fff', fontSize: 15 }}>{q.sessionRated}</b> most
            {stats && <> · {stats.labelledToday} ma</>}
          </div>
          {q.pendingWrites > 0 ? (
            <div style={{ color: '#fbbf24' }}>mentés… ({q.pendingWrites})</div>
          ) : (
            stats && <div>{stats.totalLabelled} összesen</div>
          )}
        </div>
      </header>

      <div className="ql-scroll" style={{ display: 'flex', gap: 6, padding: '4px 12px 8px', overflowX: 'auto', scrollbarWidth: 'none' }}>
        {STRATEGIES.map(s => (
          <button key={s.value} className="ql-btn" title={s.hint} onClick={() => q.setStrategy(s.value)} style={pill(q.strategy === s.value)}>
            {s.label}
          </button>
        ))}
        <span style={{ width: 1, background: 'rgba(255,255,255,0.12)', margin: '2px 2px' }} />
        <button
          className="ql-btn"
          onClick={q.toggleReveal}
          title="A modell tippje értékelés előtt (torzíthat)"
          aria-pressed={q.reveal}
          style={pill(q.reveal)}>
          {q.reveal ? <Eye size={14} /> : <EyeOff size={14} />} Modell
          <Kbd>M</Kbd>
        </button>
      </div>

      <main style={{ flex: 1, minHeight: 0, position: 'relative', background: '#000', overflow: 'hidden' }}>
        {current ? (
          <Frame item={current} zoom={zoom} reveal={q.reveal} onToggleZoom={toggleZoom} />
        ) : (
          <div style={{ height: '100%', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 12, padding: 24, textAlign: 'center', color: '#94a3b8' }}>
            {q.loading ? (
              <>
                <Loader2 className="ql-spin" size={32} />
                <span>Képek keresése…</span>
              </>
            ) : q.exhausted ? (
              <span>Ebben a módban most nincs több címkézetlen kép. Válts módot fent.</span>
            ) : (
              <button className="ql-btn" onClick={q.retry} style={pill(true)}>
                Újrapróbálás
              </button>
            )}
          </div>
        )}
      </main>

      <div style={{ padding: '6px 12px 0', fontSize: 13, minHeight: 24, overflow: 'hidden', whiteSpace: 'nowrap', textOverflow: 'ellipsis' }}>
        <LastResultLine last={q.lastResult} />
      </div>

      <div
        style={{
          display: 'grid',
          gridTemplateColumns: `repeat(${RATING_LEVELS.length}, minmax(0, 1fr))`,
          gap: 4,
          padding: '6px 10px',
          ...rowWidth,
        }}>
        {RATING_LEVELS.map(level => (
          <RateButton
            key={level.value}
            level={level}
            example={q.examples.find(e => e.rqi === level.value)}
            disabled={!current}
            onRate={q.rate}
          />
        ))}
      </div>

      <div style={{ display: 'flex', gap: 6, padding: '0 12px calc(10px + env(safe-area-inset-bottom))', ...rowWidth }}>
        <button
          className="ql-btn"
          onClick={q.undo}
          disabled={!q.canUndo}
          style={{ ...pill(false), flex: 1, justifyContent: 'center', padding: '10px 12px', fontSize: 14 }}>
          <RotateCcw size={16} /> Visszavonás <Kbd>←</Kbd>
        </button>
        <button
          className="ql-btn"
          onClick={q.skip}
          disabled={!current}
          style={{ ...pill(false), flex: 1, justifyContent: 'center', padding: '10px 12px', fontSize: 14 }}>
          Kihagyás <SkipForward size={16} /> <Kbd>→</Kbd>
        </button>
      </div>

      {q.error && (
        <div
          role="alert"
          style={{ position: 'fixed', left: 12, right: 12, top: 12, zIndex: 30, background: '#7f1d1d', color: '#fff', borderRadius: 10, padding: '10px 12px', display: 'flex', gap: 8, alignItems: 'center', fontSize: 14 }}>
          <span style={{ flex: 1 }}>{q.error}</span>
          <button className="ql-btn" onClick={q.clearError} aria-label="Bezárás" style={{ background: 'none', color: '#fff', display: 'flex' }}>
            <X size={18} />
          </button>
        </div>
      )}

      {rubricOpen && <Rubric examples={q.examples} onClose={() => setRubricOpen(false)} />}
    </div>
  )
}
