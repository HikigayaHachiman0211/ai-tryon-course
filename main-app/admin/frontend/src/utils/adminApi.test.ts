import { describe, expect, it } from 'vitest'
import { resolveAdminApiBaseUrl } from './adminApi'

describe('admin API build-time compatibility aliases', () => {
  it('prefers the current base URL and supports the legacy Voice Clone alias', () => {
    expect(resolveAdminApiBaseUrl({ VITE_ADMIN_API_BASE_URL: ' https://admin.example.test:8443 ', VITE_ADMIN_API_URL: 'https://old.example.test' })).toBe('https://admin.example.test:8443')
    expect(resolveAdminApiBaseUrl({ VITE_ADMIN_API_URL: 'https://admin.example.test:8443' })).toBe('https://admin.example.test:8443')
  })
})
