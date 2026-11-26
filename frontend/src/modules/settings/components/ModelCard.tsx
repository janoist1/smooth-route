import React from 'react'
import { Cpu } from 'lucide-react'
import { RQI_AT_OR_WORSE_SIGN, RQI_BAD_FROM } from '../../ui'
import { useSettings } from '../hooks'
import { useRqiModelInfo } from '../hooks'
import { metricsNote, modelCardStats } from '../modelCardText'

/** Read-only card describing the live RQI (DINO) model — verzió, recept, CV-pontosság. */
const ModelCard: React.FC = () => {
  const { fetchModelInfo } = useSettings()
  const info = useRqiModelInfo()

  React.useEffect(() => {
    fetchModelInfo()
  }, [fetchModelInfo])

  if (!info) return null

  const stats = modelCardStats(info, RQI_AT_OR_WORSE_SIGN, RQI_BAD_FROM)

  return (
    <section
      style={{
        marginBottom: '48px',
        padding: '24px',
        borderRadius: '16px',
        background: 'rgba(52, 211, 153, 0.06)',
        border: '1px solid rgba(52, 211, 153, 0.2)',
      }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '8px' }}>
        <div
          style={{
            width: '40px',
            height: '40px',
            borderRadius: '12px',
            background: 'rgba(52, 211, 153, 0.15)',
            color: '#34d399',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
          }}>
          <Cpu size={22} />
        </div>
        <div>
          <h2 style={{ fontSize: '1.3rem', fontWeight: 700, color: 'white' }}>
            Élő RQI-modell (DINO)
          </h2>
          <p style={{ color: '#9ca3af', fontSize: '0.85rem' }}>
            Ez a modell adja a térképen látható útminőség-pontszámot. Csak tájékoztató.
          </p>
        </div>
      </div>

      {!info.available ? (
        <p style={{ color: '#f87171', fontSize: '0.9rem', marginTop: '12px' }}>
          Nincs betöltött modell-artifact. Tanítsd/mentsd az{' '}
          <code>ml/save_model_v2.py</code> szkripttel.
        </p>
      ) : (
        <>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px', margin: '12px 0 20px' }}>
            {[
              info.version != null ? `v${info.version}` : null,
              info.backbone,
              info.recipe,
              info.head,
            ]
              .filter(Boolean)
              .map((chip, i) => (
                <span
                  key={i}
                  style={{
                    fontSize: '0.75rem',
                    color: '#a7f3d0',
                    background: 'rgba(52, 211, 153, 0.12)',
                    padding: '4px 10px',
                    borderRadius: '999px',
                    fontFamily: 'monospace',
                  }}>
                  {chip}
                </span>
              ))}
          </div>

          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))',
              gap: '12px',
            }}>
            {stats.map(s => (
              <div
                key={s.label}
                title={s.hint}
                style={{
                  background: 'rgba(255,255,255,0.03)',
                  border: '1px solid rgba(255,255,255,0.06)',
                  borderRadius: '12px',
                  padding: '12px 14px',
                }}>
                <div style={{ fontSize: '1.4rem', fontWeight: 800, color: 'white', lineHeight: 1.1 }}>
                  {s.value}
                </div>
                <div style={{ fontSize: '0.75rem', color: '#9ca3af', marginTop: '2px' }}>
                  {s.label}
                </div>
              </div>
            ))}
          </div>

          <p style={{ color: '#6b7280', fontSize: '0.75rem', marginTop: '14px' }}>
            {metricsNote(info)} Új modell csak akkor élesíthető, ha az{' '}
            <code>ml/evaluate_artifact.py</code> kapun átmegy.
          </p>
        </>
      )}
    </section>
  )
}

export default ModelCard
