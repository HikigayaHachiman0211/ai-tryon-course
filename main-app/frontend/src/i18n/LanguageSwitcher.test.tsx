import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { LanguageSwitcher } from './LanguageSwitcher'

vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: () => '言語' }) }))

describe('main language switcher', () => {
  it('is keyboard-operable and exposes all supported language labels', () => {
    const onChange = vi.fn()
    render(<LanguageSwitcher locale="ja" onChange={onChange} />)

    const select = screen.getByRole('combobox', { name: '言語' })
    expect(select).toBeInTheDocument()
    expect(screen.getByRole('option', { name: '简体中文' })).toBeInTheDocument()
    expect(screen.getByRole('option', { name: 'English' })).toBeInTheDocument()
    expect(screen.getByRole('option', { name: '日本語' })).toBeInTheDocument()

    fireEvent.change(select, { target: { value: 'ja' } })
    expect(onChange).toHaveBeenCalledWith('ja')
  })
})
