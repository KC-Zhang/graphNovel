import { defineConfig } from '@playwright/test'

export default defineConfig({
  testDir: './e2e',
  timeout: 120_000,
  expect: { timeout: 15_000 },
  fullyParallel: false,
  workers: 1,
  reporter: [['list']],
  use: {
    baseURL: 'http://127.0.0.1:3000',
    viewport: { width: 1440, height: 900 },
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
  webServer: [
    {
      command: `.venv/bin/python -c "from app import create_app; from app.models.project import ProjectManager; ProjectManager.PROJECTS_DIR='/tmp/bookmiro-e2e-projects'; create_app().run(host='127.0.0.1', port=5001, debug=False)"`,
      cwd: '../backend',
      url: 'http://127.0.0.1:5001/health',
      reuseExistingServer: true,
      timeout: 120_000,
    },
    {
      command: 'VITE_API_BASE_URL=http://127.0.0.1:5001 npm run dev -- --port 3000',
      cwd: '.',
      url: 'http://127.0.0.1:3000',
      reuseExistingServer: true,
      timeout: 120_000,
    },
  ],
})
