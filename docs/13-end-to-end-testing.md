# 13. End-to-End Testing

Playwright validates the deployed staging frontend, backend, BigQuery serving
mart and promoted MLflow artifact as one system. Unit tests remain responsible
for formula boundaries and failure branches; E2E proves the live release wiring.

## What the staging test verifies

`frontend/tests/e2e/dashboard.spec.ts` opens `/forecast` and exercises each
genuine Day +1, Day +2 and Day +3 selector. The test verifies that:

- the page and city/horizon controls render without a server error;
- the API reports `hybrid_ml_and_forecast_rules`;
- Heat and Rain are identified as learned, ERA5-validated components;
- Wind, Air Quality and River are identified as forecast-rule indicators;
- rule-derived factors do not claim a tree-spread interval;
- unavailable optional-source factors remain unavailable rather than becoming
  zero-risk values;
- the visible observed-label disclaimer remains present; and
- the API's concrete `model_version` matches `EXPECTED_MODEL_VERSION`, the
  exact candidate promoted by the same workflow run.

The test must not require every optional AQ or River source to be available.
Those feeds have an explicit nullable contract. It should require coherent
method and availability rendering in either state.

## Staging workflow order

The live E2E job runs only from `.github/workflows/ci-staging.yml` after:

1. backend tests pass;
2. a schema-v3 `ClimaSentinel_HeatRainForecaster` candidate is trained and
   registered;
3. the exact candidate passes Heat/Rain quality and artifact-contract gates;
4. `champion` is assigned to that concrete version; and
5. backend and frontend services are deployed to Railway staging.

This order matters. Running E2E before promotion can test an older cached model,
and deploying before quality gates can expose an incompatible legacy artifact.
The workflow uses a non-canceling model-promotion concurrency group to avoid two
runs moving the alias concurrently.

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

The default target is `http://localhost:3000`. Override it and, when required,
pin the expected registered-model version:

```bash
PLAYWRIGHT_TEST_BASE_URL=https://your-staging-frontend.example \
EXPECTED_MODEL_VERSION=42 \
npm run test:e2e
```

## Failure interpretation

- “Forecast unavailable” usually means the serving mart has no eligible current
  vintage or the backend rejected/failed to load the registry artifact.
- A model-version mismatch means the deployed backend did not serve the exact
  candidate promoted in that run; this is a release failure even if scores
  render.
- An unavailable AQ or River card by itself is not an E2E failure when the API
  marks it unavailable with the correct rule provenance.
- A rule card displaying model confidence bounds, or a missing validation
  disclaimer, is a contract failure.
