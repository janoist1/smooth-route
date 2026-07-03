export const ROUTES = {
  HOME: { path: '/', exact: true },
  TRAINING_LIST: { path: '/training', exact: true },
  TRAINING_REVIEW: { path: '/training/:id/review', exact: true },
  SETTINGS: { path: '/settings', exact: true },
} as const

export const buildPath = (route: { path: string }, params?: Record<string, string | number>) => {
  if (!params) return route.path
  let path = route.path
  Object.entries(params).forEach(([key, value]) => {
    path = path.replace(`:${key}`, String(value))
  })
  return path
}
