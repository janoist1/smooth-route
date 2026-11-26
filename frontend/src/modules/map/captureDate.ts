// Street View capture-date helpers (pure). The backend sends `captureDate` as
// "YYYY-MM" (month precision, null = unknown). The RQI describes the road as
// of that month, so an old image means the shown quality may be outdated.

// Images older than this are flagged on the detail card and can be dimmed on
// the map. Mirrors STALE_AFTER_YEARS in backend/app/services/capture_date.py.
export const STALE_AFTER_YEARS = 4

const YEAR_MONTH = /^(\d{4})-(\d{2})$/

interface YearMonth {
  year: number
  month: number // 1-12
}

export const parseCaptureDate = (value?: string | null): YearMonth | null => {
  if (!value) return null
  const m = YEAR_MONTH.exec(value.trim())
  if (!m) return null
  const year = Number(m[1])
  const month = Number(m[2])
  if (month < 1 || month > 12) return null
  return { year, month }
}

/** Whole months from the capture month to `now`'s month (never negative). */
export const captureAgeMonths = (value?: string | null, now: Date = new Date()): number | null => {
  const ym = parseCaptureDate(value)
  if (!ym) return null
  const months = (now.getFullYear() - ym.year) * 12 + (now.getMonth() + 1 - ym.month)
  return Math.max(0, months)
}

/** True when the image is more than `years` old. Unknown dates are not "old". */
export const isStaleCapture = (
  value?: string | null,
  now: Date = new Date(),
  years: number = STALE_AFTER_YEARS,
): boolean => {
  const months = captureAgeMonths(value, now)
  return months !== null && months > years * 12
}

/** "2019-06" as shown on the card ("ÉÉÉÉ-HH"); "ismeretlen" when unknown. */
export const formatCaptureDate = (value?: string | null): string => {
  const ym = parseCaptureDate(value)
  if (!ym) return 'ismeretlen'
  return `${ym.year}-${String(ym.month).padStart(2, '0')}`
}

/** Human age, e.g. "7 éves" / "8 hónapos" / "friss"; null when unknown. */
export const formatCaptureAge = (value?: string | null, now: Date = new Date()): string | null => {
  const months = captureAgeMonths(value, now)
  if (months === null) return null
  if (months < 1) return 'friss'
  if (months < 12) return `${months} hónapos`
  return `${Math.floor(months / 12)} éves`
}
