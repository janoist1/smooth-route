import type { ReactNode } from 'react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { Link, MemoryRouter } from 'react-router-dom'
import { ROUTES } from '../routes'
import Routes from './Routes'

vi.mock('modules/auth', () => ({
  RequireAdmin: ({ children }: { children: ReactNode }) => children,
}))
vi.mock('./HomePage', () => ({
  default: () => <div>Térkép betöltve</div>,
}))
vi.mock('./pages/SettingsPage', async () => {
  throw new TypeError('Failed to fetch dynamically imported module')
})

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

describe('Routes', () => {
  it('contains a failed admin chunk with a Hungarian fallback and keeps the map route usable', async () => {
    vi.spyOn(console, 'error').mockImplementation(() => {})
    render(
      <MemoryRouter initialEntries={[ROUTES.SETTINGS.path]}>
        <nav><Link to={ROUTES.HOME.path}>Térkép</Link></nav>
        <Routes />
      </MemoryRouter>,
    )

    expect(await screen.findByRole('alert')).toHaveTextContent('Nem sikerült betölteni az oldalt.')
    expect(screen.getByRole('button', { name: 'Újratöltés' })).toBeInTheDocument()
    fireEvent.click(screen.getByRole('link', { name: 'Térkép' }))
    expect(await screen.findByText('Térkép betöltve')).toBeInTheDocument()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })
})
