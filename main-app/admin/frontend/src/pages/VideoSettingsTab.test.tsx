import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({ get: vi.fn(), put: vi.fn(), post: vi.fn() }))
vi.mock('../utils/request', () => ({ default: mocks }))
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (key: string) => key }) }))
import VideoSettingsTab from './VideoSettingsTab'

beforeEach(() => {
  vi.clearAllMocks()
  window.matchMedia = vi.fn().mockReturnValue({ matches: false, addListener: vi.fn(), removeListener: vi.fn(), addEventListener: vi.fn(), removeEventListener: vi.fn() })
  mocks.get.mockResolvedValue({ data: { enabled: true, has_api_key: true, base_url: 'https://01router.com/api/v1', project_id: 'project-a', timeout_seconds: 60, rate_limit_per_minute: 3, daily_quota_limit: 20 } })
  mocks.put.mockResolvedValue({ data: { enabled: true, has_api_key: true } })
})
afterEach(cleanup)

it('saves the optional project and keeps an existing key when left blank', async () => {
  render(<VideoSettingsTab />)
  const project = await screen.findByLabelText('videoSettings.project')
  await waitFor(() => expect(project).toHaveValue('project-a'))
  fireEvent.change(project, { target: { value: 'project-b' } })
  fireEvent.click(screen.getByRole('button', { name: 'actions.save' }))
  await waitFor(() => expect(mocks.put).toHaveBeenCalled())
  expect(mocks.put.mock.calls[0][0]).toBe('/api/ai-config/video')
  expect(mocks.put.mock.calls[0][1]).toMatchObject({ project_id: 'project-b', enabled: true })
  expect(mocks.put.mock.calls[0][1].api_key).toBeUndefined()
})

it('uses the read-only connection check and displays its result', async () => {
  mocks.post.mockResolvedValue({ data: { success: true, status_code: 200, latency_ms: 120 } })
  render(<VideoSettingsTab />)
  fireEvent.click(await screen.findByRole('button', { name: 'videoSettings.test' }))
  await waitFor(() => expect(mocks.post).toHaveBeenCalledWith('/api/ai-config/video/test'))
  expect(await screen.findByText(/120 ms/)).toBeInTheDocument()
})
