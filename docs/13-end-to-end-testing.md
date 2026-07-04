# 13. End-to-End Testing

To ensure the highest quality of integration across the full stack (Frontend, Backend, and ML Model), ClimaSentinel utilizes **Playwright** for Automated End-to-End (E2E) testing. 

## 1. What the E2E Test Evaluates

Unlike unit tests that evaluate isolated functions, our E2E test validates the application from the exact perspective of a human user. The automated headless browser:
1. **Navigates to the Dashboard:** It loads the root URL.
2. **Validates UI Rendering:** It ensures the main "ClimaSentinel" brand title is visible.
3. **Validates Backend Connection:** It ensures the page does not return a "500 Internal Server Error" when trying to fetch data from the FastAPI and BigQuery layer.
4. **Validates Data Delivery:** It verifies that dynamic climate data (like a city card for "Paris" or the "Tipping Score" label) successfully renders on the screen.

## 2. CI/CD Integration Architecture

To ensure speed and efficiency, the E2E test runs exclusively in the **`dev → staging` CI pipeline** (`.github/workflows/ci-staging.yml`), rather than running on every pull request.

**Pipeline Flow:**
1. Code is merged into `staging`.
2. The CI pipeline builds the Docker image and deploys the backend and frontend to the Railway Staging environment.
3. The `e2e-test` CI job boots up, installs Playwright, and targets the **live deployed staging URL** using the `STAGING_FRONTEND_URL` GitHub Secret.
4. The test executes. If it fails, developers are immediately alerted that the latest release broke the staging deployment.

## 3. Directory Structure

All E2E testing logic resides in the `frontend` directory:

```text
frontend/
├── playwright.config.ts           # Playwright configuration (baseURL, timeouts, browsers)
└── tests/
    └── e2e/
        └── dashboard.spec.ts      # The core UI testing script
```

## 4. Running the Tests Locally

You can run the Playwright tests on your local machine to verify changes before pushing them.

1. Ensure your local frontend is running (`npm run dev` running on `http://localhost:3000`).
2. Open a new terminal in the `frontend/` directory.
3. Execute the test command:
   ```bash
   npm run test:e2e
   ```

By default, the local test runs against `http://localhost:3000`. If you want to test against the live production or staging URL from your local machine, you can pass the environment variable:
```bash
PLAYWRIGHT_TEST_BASE_URL=https://frontend-staging-3885.up.railway.app npm run test:e2e
```
