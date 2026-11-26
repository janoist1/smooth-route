// Phone-width breakpoint shared by the map panels. Must match the
// `@media (max-width: 600px)` block in components/roadCards.css.
export const NARROW_SCREEN_MAX_PX = 600

/** Below this height the left column (route planner + legend) gets crowded. */
export const SHORT_SCREEN_MAX_PX = 820

const matches = (query: string): boolean =>
  typeof window !== 'undefined' &&
  typeof window.matchMedia === 'function' &&
  window.matchMedia(query).matches

/** True on a phone-width viewport (false where matchMedia is unavailable). */
export const isNarrowScreen = (): boolean => matches(`(max-width: ${NARROW_SCREEN_MAX_PX}px)`)

/** Phone-width OR short: optional panels should start collapsed. */
export const isCompactScreen = (): boolean =>
  isNarrowScreen() || matches(`(max-height: ${SHORT_SCREEN_MAX_PX}px)`)
