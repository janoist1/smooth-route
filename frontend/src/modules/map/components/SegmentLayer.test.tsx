import { afterEach, describe, expect, it, vi } from 'vitest'
import { act, cleanup, render } from '@testing-library/react'
import type { RoadSegment } from '../segments/types'
import type { SegmentStyle } from '../segments/style'

const { lines, map } = vi.hoisted(() => ({
  lines: [] as Array<{
    style: Partial<SegmentStyle>
    handlers: Record<string, () => void>
    setStyle: (style: Partial<SegmentStyle>) => void
  }>,
  map: {},
}))
vi.mock('react-leaflet', () => ({ useMap: () => map }))
vi.mock('leaflet', () => ({
  default: {
    Browser: { mobile: true },
    layerGroup: () => ({ addLayer: vi.fn(), addTo: vi.fn(), remove: vi.fn() }),
    polyline: () => {
      const line = {
        style: {} as Partial<SegmentStyle>,
        handlers: {} as Record<string, () => void>,
        setStyle(style: Partial<SegmentStyle>) { Object.assign(this.style, style) },
        on(event: string, handler: () => void) { this.handlers[event] = handler },
        addTo() { return this },
        remove: vi.fn(),
        bringToBack: vi.fn(),
      }
      lines.push(line)
      return line
    },
  },
}))
import SegmentLayer from './SegmentLayer'

afterEach(() => { cleanup(); lines.length = 0 })

describe('SegmentLayer selection', () => {
  it('keeps the selected segment style through mouseover and mouseout and restores it on deselection', () => {
    const segment = {
      id: 's1', path: [[47.5, 19.04], [47.51, 19.05]], rqi: null,
      confidence: 0.2, confidenceLevel: 'low', captureDateMax: '2000-01',
    } as RoadSegment
    const props = { segments: [segment], zoom: 14, dimStale: true, interactive: true, onSelect: vi.fn() }
    const { rerender } = render(<SegmentLayer {...props} selected={segment} />)
    const line = lines[1]
    const selectedStyle = { ...line.style }
    expect(selectedStyle.opacity).toBe(1)
    act(() => { line.handlers.mouseover() })
    expect(line.style).toEqual(selectedStyle)
    act(() => { line.handlers.mouseout() })
    expect(line.style).toEqual(selectedStyle)
    rerender(<SegmentLayer {...props} selected={null} />)
    act(() => { line.handlers.mouseover(); line.handlers.mouseout() })
    expect(line.style.opacity).toBeLessThan(1)
  })
})
