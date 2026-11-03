import { defineConfig } from '@playwright/test'
import { BACKEND_DIR, BACKEND_PORT, FRONTEND_PORT, FRONTEND_URL, backendEnv, frontendEnv } from './e2e/stack'

// Needs MongoDB on localhost:27017 and GreenMail: docker compose -f docker-compose.test.yml up -d
export default defineConfig({
  testDir: './e2e',
  timeout: 60_000,
  forbidOnly: Boolean(process.env.CI),
  reporter: process.env.CI ? 'github' : 'list',
  use: { baseURL: FRONTEND_URL, trace: 'retain-on-failure' },
  projects: [
    { name: 'owner', testMatch: /owner\.setup\.ts/ },
    {
      name: 'mobile',
      dependencies: ['owner'],
      use: { viewport: { width: 375, height: 812 }, hasTouch: true, storageState: 'test-results/owner.json' },
    },
    {
      name: 'desktop',
      dependencies: ['owner'],
      use: { viewport: { width: 1280, height: 800 }, storageState: 'test-results/owner.json' },
    },
  ],
  webServer: [
    {
      command: `uv run uvicorn app.main:app --port ${BACKEND_PORT}`,
      cwd: BACKEND_DIR,
      env: backendEnv,
      url: `http://localhost:${BACKEND_PORT}/`,
      reuseExistingServer: false, // a running one would read a different mailbox
      timeout: 120_000,
    },
    {
      command: `npx next dev -p ${FRONTEND_PORT}`,
      env: frontendEnv,
      url: `${FRONTEND_URL}/sign-in`,
      reuseExistingServer: false,
      timeout: 180_000,
    },
  ],
})
