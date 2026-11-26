import { describe, it, expect, afterEach, vi } from 'vitest'
import { NARROW_SCREEN_MAX_PX, SHORT_SCREEN_MAX_PX, isCompactScreen, isNarrowScreen } from './screen'

// jsdom has no matchMedia: stub one that answers from a fake viewport size.
const stubViewport = (width: number, height: number) => {
  const matchMedia = vi.fn((query: string) => {
    const maxWidth = /max-width:\s*(\d+)px/.exec(query)
    const maxHeight = /max-height:\s*(\d+)px/.exec(query)
    const matches = maxWidth ? width <= Number(maxWidth[1]) : maxHeight ? height <= Number(maxHeight[1]) : false
    return { matches } as MediaQueryList
  })
  vi.stubGlobal('matchMedia', matchMedia)
  return matchMedia
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('screen breakpoints', () => {
  it('uses the same phone breakpoint as roadCards.css', () => {
    expect(NARROW_SCREEN_MAX_PX).toBe(600)
    const matchMedia = stubViewport(375, 812)
    isNarrowScreen()
    expect(matchMedia).toHaveBeenCalledWith('(max-width: 600px)')
  })

  it('is narrow up to and including the breakpoint', () => {
    stubViewport(NARROW_SCREEN_MAX_PX, 900)
    expect(isNarrowScreen()).toBe(true)
    stubViewport(NARROW_SCREEN_MAX_PX + 1, 900)
    expect(isNarrowScreen()).toBe(false)
  })

  it('is compact when the viewport is narrow OR short', () => {
    stubViewport(375, 900)
    expect(isCompactScreen()).toBe(true)

    // Wide but short (a laptop): not narrow, still compact.
    stubViewport(1280, SHORT_SCREEN_MAX_PX)
    expect(isNarrowScreen()).toBe(false)
    expect(isCompactScreen()).toBe(true)

    stubViewport(1280, SHORT_SCREEN_MAX_PX + 1)
    expect(isCompactScreen()).toBe(false)
  })

  it('is false where matchMedia is unavailable', () => {
    vi.stubGlobal('matchMedia', undefined)
    expect(isNarrowScreen()).toBe(false)
    expect(isCompactScreen()).toBe(false)
  })
})
