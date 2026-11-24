import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const authMocks = vi.hoisted(() => ({
  login: vi.fn(),
  getRecoveryOptions: vi.fn(),
  resetPassword: vi.fn(),
}))

vi.mock('../api/auth', () => ({
  login: authMocks.login,
  getRecoveryOptions: authMocks.getRecoveryOptions,
  resetPassword: authMocks.resetPassword,
}))

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
    i18n: { resolvedLanguage: 'zh-CN', language: 'zh-CN', changeLanguage: vi.fn() },
  }),
}))

import LoginPage from './LoginPage'

describe('LoginPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    localStorage.clear()
    Object.defineProperty(window, 'matchMedia', {
      configurable: true,
      value: () => ({
        matches: false,
        addListener: () => {},
        removeListener: () => {},
        addEventListener: () => {},
        removeEventListener: () => {},
        dispatchEvent: () => false,
      }),
    })
  })

  afterEach(() => {
    cleanup()
  })

  it('shows visible error alert when login fails with invalid credentials', async () => {
    authMocks.login.mockRejectedValueOnce({
      response: { data: { detail: 'Invalid username or password' } },
    })

    render(
      <MemoryRouter>
        <LoginPage />
      </MemoryRouter>,
    )

    fireEvent.change(screen.getByPlaceholderText('auth.username'), { target: { value: 'admin' } })
    fireEvent.change(screen.getByPlaceholderText('auth.password'), { target: { value: 'wrongpass' } })
    fireEvent.click(screen.getByRole('button', { name: 'auth.login' }))

    await waitFor(() => {
      expect(authMocks.login).toHaveBeenCalledWith('admin', 'wrongpass')
    })
    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('Invalid username or password')
  })

  it('opens forgot-password modal and submits resetPassword via recovery key', async () => {
    authMocks.getRecoveryOptions.mockResolvedValueOnce({
      data: { has_security_question: false, security_question: null, has_recovery_key: true },
    })
    authMocks.resetPassword.mockResolvedValueOnce({ data: { status: 'ok' } })

    render(
      <MemoryRouter>
        <LoginPage />
      </MemoryRouter>,
    )

    fireEvent.click(screen.getByRole('button', { name: 'auth.forgotPassword' }))

    await waitFor(() => {
      expect(authMocks.getRecoveryOptions).toHaveBeenCalledWith('admin')
    })

    fireEvent.change(screen.getByPlaceholderText('auth.recoveryKey'), { target: { value: 'my-recovery-key' } })
    fireEvent.change(screen.getByPlaceholderText('auth.newPassword'), { target: { value: 'admin123' } })
    fireEvent.change(screen.getByPlaceholderText('auth.confirmPassword'), { target: { value: 'admin123' } })
    fireEvent.click(screen.getByRole('button', { name: 'auth.resetSubmit' }))

    await waitFor(() => {
      expect(authMocks.resetPassword).toHaveBeenCalledWith({
        username: 'admin',
        method: 'recovery_key',
        proof: 'my-recovery-key',
        new_password: 'admin123',
      })
    })
  })
})
