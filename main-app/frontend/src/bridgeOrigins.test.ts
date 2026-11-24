import { describe, expect, it } from 'vitest'
import { isExactBridgeOriginAllowed } from './bridgeOrigins'

describe('three-port bridge origin contract', () => {
  it('accepts only the configured exact origin, including its port', () => {
    expect(isExactBridgeOriginAllowed('https://course.example.test', 'https://course.example.test')).toBe(true)
    expect(isExactBridgeOriginAllowed('https://course.example.test', 'https://course.example.test:8443')).toBe(false)
    expect(isExactBridgeOriginAllowed('https://course.example.test', 'https://evil.example.test')).toBe(false)
    expect(isExactBridgeOriginAllowed('https://course.example.test', '*')).toBe(false)
  })
})
