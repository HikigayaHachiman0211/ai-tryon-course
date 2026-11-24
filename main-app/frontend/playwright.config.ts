import { defineConfig, devices } from '@playwright/test'

const browsers = (process.env.E2E_BROWSERS || 'chromium')
  .split(',')
  .map((value) => value.trim())
  .filter((value): value is 'chromium' | 'firefox' | 'webkit' => ['chromium', 'firefox', 'webkit'].includes(value))

const browserDevice = (browser: string) => {
  if (browser === 'firefox') return devices['Desktop Firefox']
  if (browser === 'webkit') return devices['Desktop Safari']
  return devices['Desktop Chrome']
}

const targetProjects = [
  { name: 'main', baseURL: process.env.E2E_MAIN_URL || 'http://127.0.0.1:3000/' },
  { name: 'admin', baseURL: process.env.E2E_ADMIN_URL || 'http://127.0.0.1:3001/' },
  { name: 'workbench', baseURL: process.env.E2E_WORKBENCH_URL || 'http://127.0.0.1:8082/static/index.html' },
]

export default defineConfig({
  testDir: './e2e',
  timeout: 30_000,
  expect: { timeout: 10_000 },
  fullyParallel: true,
  reporter: process.env.CI ? [['dot'], ['html', { open: 'never' }]] : 'list',
  use: {
    baseURL: targetProjects[0].baseURL,
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
  projects: targetProjects.flatMap((target) => browsers.map((browser) => ({
    name: `${target.name}-${browser}`,
    use: { ...browserDevice(browser), baseURL: target.baseURL },
  }))),
})
