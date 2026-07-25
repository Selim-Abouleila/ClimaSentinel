# 13. End-to-End Testing

Playwright validates the deployed staging frontend, backend and BigQuery serving
mart as one system. MLflow challengers are evaluated separately. Unit tests
remain responsible for formula boundaries and failure branches; E2E proves the
live operational rule release.

## What the staging test verifies

`frontend/tests/e2e/dashboard.spec.ts` opens `/forecast` and exercises each
genuine Day +1, Day +2 and Day +3 selector. The test verifies that:

- the page and city/horizon controls render without a server error;
- the page labels the forecast as beta and describes the projections as
  experimental and rule-based;
- the API reports `forecast_rules_baseline` and
  `same_vintage_forecast_rules`;
- every factor is identified as a forecast rule;
- Heat reports `era5_backtested_limited`, Rain reports
  `era5_backtested_insufficient_skill`, and Wind, Air Quality and River report
  `not_observation_validated`;
- all component and aggregate interval fields are null;
- unavailable optional-source factors remain unavailable rather than becoming
  zero-risk values;
- the visible validation-scope disclaimer remains present; and
- `model_version` is null and no learned component is claimed by the
  operational response.

The test must not require every optional AQ or River source to be available.
Those feeds have an explicit nullable contract. It should require coherent
method and availability rendering in either state.

## Staging workflow order

The live E2E job runs only from `.github/workflows/ci-staging.yml` after:

1. backend tests pass;
2. a schema-v3 `ClimaSentinel_HeatRainForecaster` challenger is trained and
   registered;
3. the exact challenger is evaluated; quality rejection is recorded without
   moving `champion`, while operational/contract errors still fail the job;
4. backend and frontend services are deployed to Railway staging using the
   rule-baseline policy; and
5. Playwright validates the live rule response.

This order proves that challenger evaluation completed and the deployed release
remains available whether the candidate passed or was honestly rejected. The
workflow uses a non-canceling model-promotion concurrency group to prevent two
passing challengers from moving the alias concurrently.

Railway deployments run in attached mode, so the CLI waits for each service to
deploy successfully. The frontend build also includes a unique
`/releases/<commit-sha>-<workflow-run-id>.txt` marker. Before Playwright starts,
CI checks that exact marker for up to 36 attempts, including on failed-job
reruns. The test then polls the backend API for the matching
`forecast_rules_baseline:same_vintage_forecast_rules` contract before exercising
all horizons. This avoids testing an old release or a rollout in progress.

## Directory structure

```text
frontend/
├── playwright.config.ts
└── tests/
    └── e2e/
        └── dashboard.spec.ts
```

## Running locally

Start the frontend and a compatible backend, then run:

```bash
cd frontend
npm install
npx playwright install --with-deps chromium
npm run test:e2e
```

The default target is `http://localhost:3000`. Override it for a live target:

```bash
PLAYWRIGHT_TEST_BASE_URL=https://your-staging-frontend.example npm run test:e2e
```

## Failure interpretation

- “Forecast unavailable” usually means the serving mart has no eligible current
  vintage or the backend/data connection failed.
- A learned method, non-null model version or non-null interval in the
  operational response is a release-contract failure.
- An unavailable AQ or River card by itself is not an E2E failure when the API
  marks it unavailable with the correct rule provenance.
- A rule card displaying model confidence bounds, or a missing validation
  disclaimer, is a contract failure.
