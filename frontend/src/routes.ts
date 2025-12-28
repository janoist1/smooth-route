export const ROUTES = {
  HOME: { path: '/', exact: true },
  TRAINING: { path: '/training/:id', exact: true },
} as const

export const buildPath = (route: { path: string }, params?: Record<string, string | number>) => {
  if (!params) return route.path
  let path = route.path
  Object.entries(params).forEach(([key, value]) => {
    path = path.replace(`:${key}`, String(value))
  })
  return path
}
