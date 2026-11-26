import { describe, it, expect } from 'vitest'
import {
  captureAgeMonths,
  formatCaptureAge,
  formatCaptureDate,
  isStaleCapture,
  parseCaptureDate,
} from './captureDate'

// 2026-11-18 (months are 0-based in Date).
const NOW = new Date(2026, 10, 18)

describe('parseCaptureDate', () => {
  it('parses the backend "YYYY-MM" format', () => {
    expect(parseCaptureDate('2019-06')).toEqual({ year: 2019, month: 6 })
  })

  it('rejects missing or malformed values', () => {
    expect(parseCaptureDate(null)).toBeNull()
    expect(parseCaptureDate(undefined)).toBeNull()
    expect(parseCaptureDate('')).toBeNull()
    expect(parseCaptureDate('2019')).toBeNull()
    expect(parseCaptureDate('2019-13')).toBeNull()
    expect(parseCaptureDate('2019-00')).toBeNull()
    expect(parseCaptureDate('junius')).toBeNull()
  })
})

describe('captureAgeMonths', () => {
  it('counts whole months up to now', () => {
    expect(captureAgeMonths('2026-11', NOW)).toBe(0)
    expect(captureAgeMonths('2025-12', NOW)).toBe(11)
    expect(captureAgeMonths('2019-06', NOW)).toBe(89)
  })

  it('is null for unknown and never negative', () => {
    expect(captureAgeMonths(null, NOW)).toBeNull()
    expect(captureAgeMonths('2027-02', NOW)).toBe(0)
  })
})

describe('isStaleCapture', () => {
  it('flags images strictly older than 4 years', () => {
    expect(isStaleCapture('2022-11', NOW)).toBe(false) // exactly 48 months
    expect(isStaleCapture('2022-10', NOW)).toBe(true) // 49 months
    expect(isStaleCapture('2012-07', NOW)).toBe(true)
  })

  it('never treats an unknown date as old', () => {
    expect(isStaleCapture(null, NOW)).toBe(false)
    expect(isStaleCapture('garbage', NOW)).toBe(false)
  })

  it('accepts a custom threshold', () => {
    expect(isStaleCapture('2024-10', NOW, 2)).toBe(true)
    expect(isStaleCapture('2024-12', NOW, 2)).toBe(false)
  })
})

describe('formatting', () => {
  it('formats the capture month or "ismeretlen"', () => {
    expect(formatCaptureDate('2019-06')).toBe('2019-06')
    expect(formatCaptureDate(null)).toBe('ismeretlen')
  })

  it('formats a human age', () => {
    expect(formatCaptureAge('2026-11', NOW)).toBe('friss')
    expect(formatCaptureAge('2026-03', NOW)).toBe('8 hónapos')
    expect(formatCaptureAge('2019-06', NOW)).toBe('7 éves')
    expect(formatCaptureAge(null, NOW)).toBeNull()
  })
})
