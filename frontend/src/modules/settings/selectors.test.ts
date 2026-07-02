import { describe, it, expect } from 'vitest'
import type { RootState } from '../../store'
import { selectRqiDisplaySource } from './selectors'

const stateWith = (value?: string): RootState =>
  ({
    settings: { items: value ? [{ key: 'rqi_display_source', value }] : [] },
  }) as unknown as RootState

describe('selectRqiDisplaySource', () => {
  it('returns the configured source', () => {
    expect(selectRqiDisplaySource(stateWith('dino'))).toBe('dino')
    expect(selectRqiDisplaySource(stateWith('yolo'))).toBe('yolo')
  })

  it('defaults to "both" when the setting is missing or invalid', () => {
    expect(selectRqiDisplaySource(stateWith())).toBe('both')
    expect(selectRqiDisplaySource(stateWith('garbage'))).toBe('both')
  })
})
