import { defineConfig, devices } from '@playwright/test';
export default defineConfig({
  testDir: './tests/ui',
  timeout: 45000,
  expect: { timeout: 7000 },
  workers: 1,
  outputDir: 'outputs/ui-results',
  reporter: [['list']],
  use: {
    baseURL: process.env.PLAYWRIGHT_BASE_URL || 'http://127.0.0.1:18765',
    channel:
      process.env.PLAYWRIGHT_CHANNEL || (process.platform === 'win32' ? 'msedge' : undefined),
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
  projects: [
    { name: 'desktop', use: { viewport: { width: 1440, height: 1000 } } },
    { name: 'mobile', use: { ...devices['Pixel 7'] } },
  ],
});
