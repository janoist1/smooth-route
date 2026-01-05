export const getColorForRqi = (score: number) => {
  if (score <= 2.0) return '#22c55e' // Green (Good)
  if (score <= 3.5) return '#facc15' // Yellow (Medium)
  return '#ef4444' // Red (Bad)
}

export const getColorForLabel = (label: string) => {
  switch (label) {
    case 'pothole':
      return '#ef4444' // Red
    case 'patch':
      return '#facc15' // Yellow
    case 'shadow':
      return '#3b82f6' // Blue
    case 'long_crack':
    case 'trans_crack':
    case 'alligator_crack':
      return '#a855f7' // Purple
    case 'degradation':
      return '#f97316' // Orange
    case 'manhole':
      return '#10b981' // Green
    case 'marking':
      return '#06b6d4' // Cyan
    case 'ignore':
      return '#ec4899' // Pink/Magenta for excluded zones
    default:
      return '#fff'
  }
}

export const getRgbForLabel = (label: string) => {
  switch (label) {
    case 'pothole':
      return '239, 68, 68'
    case 'patch':
      return '250, 204, 21'
    case 'shadow':
      return '59, 130, 246'
    case 'long_crack':
    case 'trans_crack':
    case 'alligator_crack':
      return '168, 85, 247'
    case 'degradation':
      return '249, 115, 22'
    case 'manhole':
      return '16, 185, 129'
    case 'marking':
      return '6, 182, 212'
    case 'ignore':
      return '236, 72, 153'
    default:
      return '255, 255, 255'
  }
}
