// Clerk is optional at build time: without a publishable key the app runs in
// anonymous mode (no sign-in UI); the backend decides what anonymous may do.
export const CLERK_PUBLISHABLE_KEY: string = import.meta.env.VITE_CLERK_PUBLISHABLE_KEY ?? ''

export const authEnabled: boolean = CLERK_PUBLISHABLE_KEY.length > 0
