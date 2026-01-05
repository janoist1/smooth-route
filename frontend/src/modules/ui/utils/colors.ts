export const getRQIColor = (score?: number | null): string => {
  if (score === undefined || score === null) return '#888' // Gray for unknown
  if (score <= 2.0) return '#4ade80' // Green (Good)
  if (score <= 3.0) return '#facc15' // Yellow (Fair)
  if (score <= 4.0) return '#f87171' // Red (Poor)
  return '#ef4444' // Dark Red (Very Poor)
}
