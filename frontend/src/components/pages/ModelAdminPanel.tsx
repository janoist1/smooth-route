import React, { useEffect, useState } from 'react'
import { useMutation, useQuery } from '@apollo/client/react'
import { useDispatch, useSelector } from 'react-redux'
import { gql } from 'modules/graphql'
import { actions as apiActions, selectJob } from 'modules/api'
import { rqiLevel } from 'modules/ui'
import type { RootState } from '../../store'

const MODEL_ADMIN = gql(`
  query ModelAdmin {
    modelAdmin {
      trainedOn
      newLabels
      newByArea {
        area
        count
      }
      newByLevel {
        level
        count
      }
      sprintLabelled
      sprintTarget
      hint
      candidateAvailable
      report
      reportVerdict
      reportGatePass
      reportAt
      confirmPhrase
    }
  }
`)

const START_RETRAIN = gql(`
  mutation StartRetrain {
    startRetrain
  }
`)

const PROMOTE = gql(`
  mutation PromoteCandidate($confirm: String!) {
    promoteCandidate(confirm: $confirm)
  }
`)

const RESCORE = gql(`
  mutation StartRescoreAndRebuild {
    startRescoreAndRebuild
  }
`)

const AREA_HU: Record<string, string> = {
  budapest: 'Budapest',
  torokbalint: 'Törökbálint–Budaörs',
  szekesfehervar: 'Székesfehérvár',
  tapolca: 'Tapolca',
  other: 'Új terület',
}

const card: React.CSSProperties = {
  background: 'rgba(255,255,255,0.05)',
  border: '1px solid rgba(255,255,255,0.1)',
  borderRadius: 16,
  padding: 20,
}

const button = (bg: string, disabled = false): React.CSSProperties => ({
  background: disabled ? 'rgba(255,255,255,0.08)' : bg,
  color: disabled ? '#6b7280' : '#fff',
  border: 'none',
  borderRadius: 10,
  padding: '10px 14px',
  fontWeight: 600,
  cursor: disabled ? 'default' : 'pointer',
})

const Bar: React.FC<{ value: number; max: number; color?: string }> = ({ value, max, color = '#3b82f6' }) => (
  <div style={{ height: 8, borderRadius: 4, background: 'rgba(255,255,255,0.1)', overflow: 'hidden' }}>
    <div style={{ width: `${Math.min(100, max > 0 ? (value / max) * 100 : 0)}%`, height: '100%', background: color }} />
  </div>
)

/** Follows a background job over the existing SSE stream (api module). */
const useJob = (jobId: string | null) => {
  const dispatch = useDispatch()
  useEffect(() => {
    if (jobId) dispatch(apiActions.registerJob(jobId))
  }, [dispatch, jobId])
  return useSelector((state: RootState) => selectJob(state, jobId))
}

/**
 * Admin "Modell" panel (T-68): label progress since the champion, one-click
 * retrain + spatial gate report, and promotion behind an explicit
 * confirmation. Promotion never happens automatically.
 */
const ModelAdminPanel: React.FC = () => {
  const { data, refetch } = useQuery(MODEL_ADMIN, { fetchPolicy: 'no-cache' })
  const [startRetrain] = useMutation(START_RETRAIN)
  const [promote] = useMutation(PROMOTE)
  const [rescore] = useMutation(RESCORE)
  const [jobId, setJobId] = useState<string | null>(null)
  const [confirmOpen, setConfirmOpen] = useState(false)
  const [confirmText, setConfirmText] = useState('')
  const [message, setMessage] = useState<string | null>(null)
  const [promoted, setPromoted] = useState(false)
  const job = useJob(jobId)
  const running = job?.status === 'running' || job?.status === 'pending'

  useEffect(() => {
    if (job?.status === 'completed' || job?.status === 'failed') void refetch()
  }, [job?.status, refetch])

  const m = data?.modelAdmin
  if (!m) return null

  const run = async (fn: () => Promise<string | undefined>) => {
    setMessage(null)
    try {
      const id = await fn()
      if (id) setJobId(id)
    } catch (e) {
      setMessage(e instanceof Error ? e.message : String(e))
    }
  }

  const doPromote = async () => {
    try {
      const res = await promote({ variables: { confirm: confirmText } })
      setMessage(res.data?.promoteCandidate ?? 'Élesítve.')
      setPromoted(true)
      setConfirmOpen(false)
      setConfirmText('')
      void refetch()
    } catch (e) {
      setMessage(e instanceof Error ? e.message : String(e))
    }
  }

  return (
    <div style={{ ...card, display: 'flex', flexDirection: 'column', gap: 14 }}>
      <h3 style={{ fontSize: '1rem' }}>Modell: címkék, újratanítás, élesítés</h3>

      <div>
        <div style={{ fontSize: '0.9rem', marginBottom: 6 }}>
          <b>{m.newLabels}</b> új címke a bajnok modell óta (az {m.trainedOn} képen tanult).
        </div>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, fontSize: '0.8rem' }}>
          {m.newByLevel.map(l => {
            const level = rqiLevel(l.level)
            return (
              <span key={l.level} style={{ border: `1px solid ${level?.color ?? '#666'}`, borderRadius: 999, padding: '2px 8px' }}>
                {level?.label_hu ?? l.level}: {l.count}
              </span>
            )
          })}
        </div>
        <div style={{ fontSize: '0.8rem', color: '#9ca3af', marginTop: 6 }}>
          {m.newByArea.length === 0
            ? 'Még nincs új címke.'
            : m.newByArea.map(a => `${AREA_HU[a.area] ?? a.area}: ${a.count}`).join(' · ')}
        </div>
      </div>

      <div>
        <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.8rem', color: '#9ca3af' }}>
          <span>Címkéző sprint</span>
          <span>
            {m.sprintLabelled} / {m.sprintTarget}
          </span>
        </div>
        <Bar value={m.sprintLabelled} max={m.sprintTarget} />
        <div style={{ fontSize: '0.8rem', color: '#cbd5e1', marginTop: 6 }}>{m.hint}</div>
      </div>

      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
        <button
          style={button('#2563eb', running)}
          disabled={running}
          onClick={() => run(async () => (await startRetrain()).data?.startRetrain)}>
          Újratanítás és mérés
        </button>
        <button
          style={button('#16a34a', running || !m.candidateAvailable || !m.reportGatePass)}
          disabled={running || !m.candidateAvailable || !m.reportGatePass}
          title={!m.reportGatePass ? 'Csak térbeli kapun átment jelölt élesíthető' : undefined}
          onClick={() => setConfirmOpen(true)}>
          Élesítés…
        </button>
        {promoted && (
          <button
            style={button('#7c3aed', running)}
            disabled={running}
            onClick={() => run(async () => (await rescore()).data?.startRescoreAndRebuild)}>
            Képek újrapontozása + szakaszok újraépítése
          </button>
        )}
      </div>

      {job && (
        <div role="status" style={{ fontSize: '0.8rem', color: '#cbd5e1' }}>
          <Bar value={job.progress} max={100} color={job.status === 'failed' ? '#ef4444' : '#3b82f6'} />
          <div style={{ marginTop: 4 }}>
            {job.status === 'failed' ? `Hiba: ${job.error ?? job.message}` : job.message}
          </div>
        </div>
      )}

      {message && <div style={{ fontSize: '0.85rem', color: '#fde68a' }}>{message}</div>}

      <div>
        <div style={{ fontSize: '0.8rem', color: '#9ca3af', marginBottom: 4 }}>
          Legutóbbi mérés{m.reportAt ? ` (${m.reportAt})` : ''}
        </div>
        <ul style={{ margin: 0, paddingLeft: 18, fontSize: '0.85rem', lineHeight: 1.5 }}>
          {m.report.map((line, i) => (
            <li
              key={i}
              style={{ color: i === 0 && m.reportVerdict !== null ? (m.reportVerdict ? '#4ade80' : '#f87171') : '#d1d5db' }}>
              {line}
            </li>
          ))}
        </ul>
      </div>

      {confirmOpen && (
        <div
          role="dialog"
          aria-label="Élesítés megerősítése"
          style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.6)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 10000, padding: 16 }}>
          <div style={{ ...card, background: '#111827', maxWidth: 420, display: 'flex', flexDirection: 'column', gap: 10 }}>
            <b>A jelölt modell élesítése</b>
            <span style={{ fontSize: '0.85rem', color: '#cbd5e1' }}>
              A jelenlegi modell időbélyeges mentésbe kerül, a jelölt lesz az éles. Utána érdemes újrapontozni a képeket.
              Megerősítéshez írd be: <b>{m.confirmPhrase}</b>
            </span>
            <input
              value={confirmText}
              onChange={e => setConfirmText(e.target.value)}
              aria-label="Megerősítő szöveg"
              style={{ padding: 8, borderRadius: 8, border: '1px solid #374151', background: '#0b0d12', color: '#fff' }}
            />
            <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
              <button style={button('#374151')} onClick={() => setConfirmOpen(false)}>
                Mégse
              </button>
              <button
                style={button('#16a34a', confirmText.trim() !== m.confirmPhrase)}
                disabled={confirmText.trim() !== m.confirmPhrase}
                onClick={doPromote}>
                Élesítés
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

export default ModelAdminPanel
