import { describe, expect, it } from 'vitest'
import { metricsNote, modelCardStats } from './modelCardText'
import type { RqiModelInfo } from './types'

const spatial: RqiModelInfo = {
  available: true,
  qwk: 0.774,
  mae: 0.405,
  exactAcc: 0.61,
  badRoadAcc: 0.86,
  badRoadAuc: 0.934,
  nTrain: 1903,
  metricsSource: 'spatial_cv',
  metricsMeasuredOn: '2026-11-26',
  segmentQwk: 0.843,
  segmentLengthM: 200,
  newAreaQwk: 0.663,
}

describe('model card texts', () => {
  it('labels the honest spatial numbers plainly', () => {
    const stats = modelCardStats(spatial, '≤', 3)
    expect(stats.slice(0, 3).map(s => [s.label, s.value])).toEqual([
      ['Új helyszíneken mért pontosság (QWK)', '0.774'],
      ['Útszakaszon (200 m, QWK)', '0.843'],
      ['Teljesen új régióban (QWK)', '0.663'],
    ])
    expect(stats.find(s => s.label === 'Rossz-út AUC')?.value).toBe('0.934')
    expect(stats.find(s => s.label === 'Jó/rossz döntés')?.hint).toBe('rossz út (RQI≤3) felismerése')
    expect(metricsNote(spatial)).toContain('olyan utcákon mérve, amelyeket a modell a tanításkor sosem látott')
    expect(metricsNote(spatial)).toContain('(mérve: 2026-11-26)')
  })

  it('falls back to the artifact numbers with a caveat', () => {
    const legacy: RqiModelInfo = { available: true, qwk: 0.895, metricsSource: 'artifact' }
    const stats = modelCardStats(legacy, '≤', 3)
    expect(stats[0]).toMatchObject({ label: 'QWK', value: '0.895' })
    expect(stats.some(s => s.label.startsWith('Új helyszíneken'))).toBe(false)
    expect(metricsNote(legacy)).toContain('optimisták lehetnek')
  })

  it('shows nothing for a missing model', () => {
    expect(modelCardStats({ available: false }, '≤', 3)).toEqual([])
  })
})
