// Where the Clerk island portals its sign-in / user button: the nav renders an
// empty slot (UserMenu) and registers its DOM node here.
import { useSyncExternalStore } from 'react'

let slot: HTMLElement | null = null
const listeners = new Set<() => void>()

export const setUserMenuSlot = (el: HTMLElement | null): void => {
  if (slot === el) return
  slot = el
  listeners.forEach(listener => listener())
}

const subscribe = (listener: () => void) => {
  listeners.add(listener)
  return () => listeners.delete(listener)
}

export const useUserMenuSlot = (): HTMLElement | null => useSyncExternalStore(subscribe, () => slot, () => null)
