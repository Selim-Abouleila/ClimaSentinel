import { defineConfig, devices } from '@playwright/test';
import path from 'node:path';

const frontendUrl = 'http://127.0.0.1:4318';
const fixtureApiUrl = 'http://127.0.0.1:4319';

export default defineConfig({
  testDir: './tests/cold-ui',
  testMatch: '**/*.spec.ts',
  outputDir: './test-results/cold-ui',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: 0,
  workers: 2,
  reporter: 'line',
  timeout: 30_000,
  use: {
    baseURL: frontendUrl,
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
  webServer: [
    {
      name: 'Cold fixture API',
      command: 'node tests/cold-ui/fixture-api.mjs',
      url: `${fixtureApiUrl}/health`,
      reuseExistingServer: false,
      timeout: 30_000,
    },
    {
      name: 'Cold local frontend',
      command: 'node tests/cold-ui/next-server.mjs',
      url: `${frontendUrl}/city/zero_fr`,
      reuseExistingServer: false,
      timeout: 120_000,
      env: {
        NEXT_PUBLIC_API_URL: fixtureApiUrl,
        NEXT_TELEMETRY_DISABLED: '1',
        NEXT_FONT_GOOGLE_MOCKED_RESPONSES: path.resolve(__dirname, 'tests/cold-ui/font-responses.cjs'),
      },
    },
  ],
});
