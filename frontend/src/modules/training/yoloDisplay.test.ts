import { describe, expect, it } from 'vitest'
import reducer from './slice'
import { YOLO_DISPLAY_CONF, YOLO_INDICATIVE_NOTE_HU, hasAiSuggestions } from './yoloDisplay'

describe('YOLO display rule', () => {
  it('starts the auto-detect threshold at the display threshold (0.5)', () => {
    expect(YOLO_DISPLAY_CONF).toBe(0.5)
    const state = reducer(undefined, { type: '@@init' })
    expect(state.autoDetectConf).toBe(YOLO_DISPLAY_CONF)
  })

  it('flags AI suggestions only (polygons with a score)', () => {
    expect(hasAiSuggestions([{ score: 0.7 }, {}])).toBe(true)
    expect(hasAiSuggestions([{}, { score: undefined }])).toBe(false)
    expect(hasAiSuggestions([])).toBe(false)
  })

  it('pins the Hungarian note', () => {
    expect(YOLO_INDICATIVE_NOTE_HU).toBe(
      'Tájékoztató jellegű: a hibafelismerő modell még kevés jelölt képből tanult.',
    )
  })
})
