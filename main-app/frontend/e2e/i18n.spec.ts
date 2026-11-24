import { test, expect } from '@playwright/test'

const locales = ['zh-CN', 'en', 'ja'] as const

test.describe('trilingual locale smoke', () => {
  test.beforeEach(async ({ page }, testInfo) => {
    void page
    test.skip(!process.env.RUN_E2E, 'Set RUN_E2E=1 after local services are running.')
    testInfo.annotations.push({ type: 'locale-contract', description: 'Every target must expose a locale switcher.' })
  })

  for (const locale of locales) {
    test(`initial ${locale} route is localized`, async ({ page }) => {
      await page.goto(`/?lang=${locale}`, { waitUntil: 'domcontentloaded' })
      await expect.poll(() => page.locator('html').getAttribute('lang')).toBe(locale)
      await expect(page.getByTestId('language-switcher')).toHaveValue(locale)
      await expect(page.locator('body')).not.toContainText(/(?:common|layout|errors|dashboard)\.[a-zA-Z]/)
    })
  }

  test('switcher persists across refresh', async ({ page }) => {
    await page.goto('/?lang=zh-CN', { waitUntil: 'domcontentloaded' })
    const switcher = page.getByTestId('language-switcher')
    await switcher.selectOption('en')
    await expect.poll(() => page.locator('html').getAttribute('lang')).toBe('en')
    await page.reload({ waitUntil: 'domcontentloaded' })
    await expect.poll(() => page.locator('html').getAttribute('lang')).toBe('en')
    await expect(switcher).toHaveValue('en')
  })
})
