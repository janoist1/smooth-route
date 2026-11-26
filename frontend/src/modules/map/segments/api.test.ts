import { describe, it, expect, afterEach, vi } from 'vitest'
import {
  SegmentApiUnsupportedError,
  errorText,
  isUnknownFieldError,
  loadSegmentMocks,
  segmentMocksEnabled,
} from './api'

describe('errorText', () => {
  it('is empty for no error and returns a string error as it is', () => {
    expect(errorText(null)).toBe('')
    expect(errorText(undefined)).toBe('')
    expect(errorText('boom')).toBe('boom')
  })

  it('reads the message of a plain Error', () => {
    expect(errorText(new Error('Failed to fetch'))).toBe('Failed to fetch')
  })

  it('collects the texts Apollo spreads over message, body, errors and result', () => {
    const error = {
      message: 'Response not successful: Received status code 400',
      bodyText: 'raw body',
      errors: [{ message: 'first' }, null, { message: 42 }, { message: 'second' }],
      result: { errors: [{ message: 'in result' }] },
    }
    expect(errorText(error)).toBe(
      'Response not successful: Received status code 400 | raw body | first | second | {"errors":[{"message":"in result"}]}',
    )
  })

  it('takes a string result verbatim and skips non-string parts', () => {
    expect(errorText({ message: 7, result: 'plain text result' })).toBe('plain text result')
    expect(errorText({})).toBe('')
  })
})

describe('isUnknownFieldError', () => {
  const validation = 'Cannot query field "roadSegments" on type "Query".'

  it('recognises GraphQL validation rejecting the field', () => {
    expect(isUnknownFieldError(new Error(validation), 'roadSegments')).toBe(true)
    expect(isUnknownFieldError(validation.toUpperCase().replace('ROADSEGMENTS', 'roadSegments'), 'roadSegments')).toBe(true)
  })

  it('finds the message inside an HTTP 400 body', () => {
    const http400 = { message: 'Received status code 400', result: { errors: [{ message: validation }] } }
    expect(isUnknownFieldError(http400, 'roadSegments')).toBe(true)
    expect(isUnknownFieldError({ message: 'x', errors: [{ message: validation }] }, 'roadSegments')).toBe(true)
  })

  it('is false for another field and for unrelated errors', () => {
    expect(isUnknownFieldError(new Error(validation), 'routeQuality')).toBe(false)
    expect(isUnknownFieldError(new Error('roadSegments timed out'), 'roadSegments')).toBe(false)
    expect(isUnknownFieldError(null, 'roadSegments')).toBe(false)
  })
})

describe('SegmentApiUnsupportedError', () => {
  it('names the missing query', () => {
    const error = new SegmentApiUnsupportedError('roadSegments')
    expect(error).toBeInstanceOf(Error)
    expect(error.name).toBe('SegmentApiUnsupportedError')
    expect(error.message).toBe('The server does not know the roadSegments query yet')
  })
})

describe('segmentMocksEnabled', () => {
  afterEach(() => {
    vi.unstubAllEnvs()
    window.history.replaceState(null, '', '/')
  })

  it('is on with VITE_MOCK_SEGMENTS=1', () => {
    vi.stubEnv('VITE_MOCK_SEGMENTS', '1')
    expect(segmentMocksEnabled()).toBe(true)
  })

  it('is off by default', () => {
    vi.stubEnv('VITE_MOCK_SEGMENTS', '')
    expect(segmentMocksEnabled()).toBe(false)
  })

  it('the ?mockSegments=1 switch works in the dev server only', () => {
    vi.stubEnv('VITE_MOCK_SEGMENTS', '')
    window.history.replaceState(null, '', '/?mockSegments=1')

    vi.stubEnv('DEV', true)
    expect(segmentMocksEnabled()).toBe(true)

    vi.stubEnv('DEV', false)
    expect(segmentMocksEnabled()).toBe(false)
  })

  it('any other value of the URL switch leaves the mocks off', () => {
    vi.stubEnv('VITE_MOCK_SEGMENTS', '')
    vi.stubEnv('DEV', true)
    window.history.replaceState(null, '', '/?mockSegments=0')
    expect(segmentMocksEnabled()).toBe(false)
  })
})

describe('loadSegmentMocks', () => {
  it('lazy-loads the mock module with both stand-in queries', async () => {
    const mocks = await loadSegmentMocks()
    expect(typeof mocks.mockRoadSegments).toBe('function')
    expect(typeof mocks.mockRouteQuality).toBe('function')
  })
})
