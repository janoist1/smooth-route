import { describe, it, expect } from 'vitest'
import {
  captureStaleness,
  confidenceExplanation,
  confidenceLabelHu,
  formatCaptureRange,
  formatDecimal,
  formatKm,
  formatLength,
  formatPercent,
  formatScore,
  highwayLabelHu,
  rqiLabelHu,
  segmentTitle,
} from './labels'

// 2026-11-18 (months are 0-based in Date).
const NOW = new Date(2026, 10, 18)

describe('rqiLabelHu', () => {
  it('names the four quality classes in Hungarian', () => {
    expect(rqiLabelHu(1)).toBe('Kiváló')
    expect(rqiLabelHu(2)).toBe('Jó')
    expect(rqiLabelHu(3)).toBe('Közepes')
    expect(rqiLabelHu(4)).toBe('Rossz')
  })

  it('uses the same bands as getRQILabel for continuous scores', () => {
    expect(rqiLabelHu(1.5)).toBe('Kiváló')
    expect(rqiLabelHu(1.6)).toBe('Jó')
    expect(rqiLabelHu(2.5)).toBe('Jó')
    expect(rqiLabelHu(2.6)).toBe('Közepes')
    expect(rqiLabelHu(3.6)).toBe('Rossz')
    expect(rqiLabelHu(4.8)).toBe('Nagyon rossz')
  })

  it('says "Nincs adat" for a missing score', () => {
    expect(rqiLabelHu(null)).toBe('Nincs adat')
    expect(rqiLabelHu(undefined)).toBe('Nincs adat')
  })
})

describe('confidence wording', () => {
  it('translates the level', () => {
    expect(confidenceLabelHu('high')).toBe('magas')
    expect(confidenceLabelHu('medium')).toBe('közepes')
    expect(confidenceLabelHu('low')).toBe('alacsony')
    expect(confidenceLabelHu('weird')).toBe('ismeretlen')
    expect(confidenceLabelHu(null)).toBe('ismeretlen')
  })

  it('explains the level in one sentence based on the frame count', () => {
    expect(confidenceExplanation('high', 24)).toBe(
      '24 képkocka alapján; a képek egybehangzóan ugyanazt mutatják.',
    )
    expect(confidenceExplanation('medium', 9)).toBe(
      '9 képkocka alapján; a képek nem teljesen egyeznek, vagy kevés a kép.',
    )
    expect(confidenceExplanation('low', 2)).toBe(
      '2 képkocka alapján; kevés a kép, vagy a becslések ellentmondanak – kezeld fenntartással.',
    )
  })

  it('handles zero frames and unknown levels', () => {
    expect(confidenceExplanation('low', 0)).toBe('Nincs hozzá képkocka – a becslés nem ellenőrizhető.')
    expect(confidenceExplanation('weird', 5)).toBe('5 képkocka alapján.')
  })
})

describe('road naming', () => {
  it('translates OSM highway tags', () => {
    expect(highwayLabelHu('residential')).toBe('lakóutca')
    expect(highwayLabelHu('primary')).toBe('főút')
    expect(highwayLabelHu('motorway')).toBe('autópálya')
    expect(highwayLabelHu('living_street')).toBe('lakó-pihenő övezet')
  })

  it('shows an unknown tag readably and null for none', () => {
    expect(highwayLabelHu('bus_guideway')).toBe('bus guideway')
    expect(highwayLabelHu(null)).toBeNull()
    expect(highwayLabelHu('')).toBeNull()
  })

  it('titles a segment by name, then by road type, then generically', () => {
    expect(segmentTitle({ roadName: 'Váci út', highway: 'primary' })).toBe('Váci út')
    expect(segmentTitle({ roadName: '  ', highway: 'residential' })).toBe('Lakóutca (névtelen)')
    expect(segmentTitle({ roadName: null, highway: null })).toBe('Névtelen útszakasz')
  })
})

describe('number formatting', () => {
  it('uses the Hungarian decimal comma', () => {
    expect(formatDecimal(2.25)).toBe('2,3')
    expect(formatDecimal(2, 2)).toBe('2,00')
    expect(formatScore(2.34)).toBe('2,3')
    expect(formatScore(null)).toBe('–')
  })

  it('formats a length in metres or kilometres', () => {
    expect(formatLength(85.4)).toBe('85 m')
    expect(formatLength(999)).toBe('999 m')
    expect(formatLength(1240)).toBe('1,2 km')
    expect(formatLength(12400)).toBe('12 km')
    expect(formatLength(null)).toBe('–')
    expect(formatLength(-5)).toBe('–')
  })

  it('formats route totals always in kilometres', () => {
    expect(formatKm(430)).toBe('0,4 km')
    expect(formatKm(62380)).toBe('62,4 km')
    expect(formatKm(undefined)).toBe('–')
  })

  it('formats a ratio as a whole percent, clamped', () => {
    expect(formatPercent(0.127)).toBe('13%')
    expect(formatPercent(0)).toBe('0%')
    expect(formatPercent(1.4)).toBe('100%')
    expect(formatPercent(null)).toBe('–')
  })
})

describe('capture date range', () => {
  it('formats a range, a single month, a half-known range and unknown', () => {
    expect(formatCaptureRange('2019-06', '2023-08')).toBe('2019-06 – 2023-08')
    expect(formatCaptureRange('2021-05', '2021-05')).toBe('2021-05')
    expect(formatCaptureRange(null, '2023-08')).toBe('2023-08')
    expect(formatCaptureRange('2019-06', null)).toBe('2019-06')
    expect(formatCaptureRange(null, null)).toBe('ismeretlen')
    expect(formatCaptureRange('garbage', undefined)).toBe('ismeretlen')
  })

  it('classifies staleness with the 4-year rule of the point card', () => {
    expect(captureStaleness('2012-07', '2019-06', NOW)).toBe('all') // newest is old too
    expect(captureStaleness('2019-06', '2025-08', NOW)).toBe('some') // only the oldest
    expect(captureStaleness('2024-01', '2025-08', NOW)).toBe('none')
    expect(captureStaleness(null, null, NOW)).toBe('none') // unknown is not "old"
  })

  it('falls back to the known end when one date is missing', () => {
    expect(captureStaleness('2015-01', null, NOW)).toBe('all')
    expect(captureStaleness(null, '2015-01', NOW)).toBe('all')
    expect(captureStaleness(null, '2025-01', NOW)).toBe('none')
  })
})
