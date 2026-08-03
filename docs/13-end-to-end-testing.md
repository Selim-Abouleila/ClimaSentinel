# 13. End-to-End Testing

Playwright provides one live staging smoke path through the forecast frontend,
backend and BigQuery serving mart. MLflow challengers are evaluated separately.
Unit tests remain responsible for formula boundaries and failure branches. This
test increases confidence in the live rule policy, but it is not a complete
release, browser, city or failure-mode test suite.

## What the staging test verifies

`frontend/tests/e2e/dashboard.spec.ts` opens `/forecast`, selects Paris and
exercises each genuine Day +1, Day +2 and Day +3 selector in desktop Chromium.
The test verifies that:

- the page and city/horizon controls render without a server error;
- the forecast selector remains exactly the original 10 eligible cities, in its
  declared order, rather than inheriting the 20-city operational registry;
- the page labels the forecast as beta and describes the projections as
  experimental and rule-based;
- the API reports `forecast_rules_baseline` and
  `same_vintage_forecast_rules`;
- every factor is identified as a forecast rule in the API response;
- Heat reports `era5_backtested_limited`, Rain reports
  `era5_backtested_insufficient_skill`, and Wind, Air Quality and River report
  `not_observation_validated`;
- all component and aggregate interval fields are null;
- optional-source factors follow the nullable API contract in whichever
  available or unavailable state the live data happens to provide;
- the visible validation-scope disclaimer remains present; and
- `model_version` is null and no learned component is claimed by the
  operational response.

The test does not force an AQ or River outage. If the live source is available,
the unavailable UI branch is not exercised. It also does not assert visible
per-factor method or validation labels; the current page presents validation
scope in one global note and checks detailed provenance in the API payload.

## Staging workflow order

The live E2E job runs only from `.github/workflows/ci-staging.yml` after:

1. the full `backend/tests/` pytest suite passes;
2. a schema-v3 `ClimaSentinel_HeatRainForecaster` challenger is trained and
   registered;
3. the exact challenger is evaluated; quality rejection is recorded without
   moving `champion`, while operational/contract errors still fail the job;
4. backend and frontend services are deployed to Railway staging using the
   rule-baseline policy; and
5. Playwright validates the live rule response.

This order proves that challenger evaluation completed before the smoke test and
that the rule-baseline path remained available whether the candidate passed or
was honestly rejected. The workflow uses a non-canceling model-promotion
concurrency group to prevent two passing challengers from moving the alias
concurrently.

Railway deployments run in attached mode, so the CLI waits for each service to
deploy successfully. The frontend build also includes a unique
`/releases/<commit-sha>-<workflow-run-id>.txt` marker. Before Playwright starts,
CI checks that exact marker for up to 36 attempts, including on failed-job
reruns. The test then polls the backend API for the compatible
`forecast_rules_baseline:same_vintage_forecast_rules` contract before exercising
all horizons.

The marker pins only the **frontend** commit and workflow run. The backend has no
equivalent commit/run endpoint; the poll proves a compatible contract, not that
the backend was built from the same commit. The BigQuery mart is likewise live
state rather than a release-stamped artifact. An older backend that already
serves the same contract can therefore pass.

The workflow's first step is the backend pytest suite only. Neither that step
nor Playwright runs `dbt parse/build/test`, verifies warehouse lineage, or
asserts when the live mart was last rebuilt. The smoke path consuming a valid
live row is therefore not evidence of mart freshness.

It also does not execute the GCP ingestion job or prove that the operational
overview contains all 20 active cities. The city registry, 240-row normals seed
and frozen forecast allowlist are checked by the PR-to-`dev` workflow, not by
this live staging browser path.

## Deliberate scope limits

The current smoke test does not cover:

- the other nine forecast-eligible cities;
- the 10 dashboard-only additions or the complete 20-city operational
  coverage;
- the `/` overview or any `/city/[city_id]` detail page;
- Firefox, WebKit, mobile layouts or accessibility conformance;
- a deliberately missing AQ/River feed or other injected backend failure;
- authentication, rate limiting, readiness or monitoring; or
- exact backend commit identity;
- dbt contracts, lineage or live-mart freshness;
- exact rendered score values against the corresponding API fields; or
- screenshot-based visual regression.

These are coverage gaps, not claims that those paths are broken.

## Directory structure

```text
frontend/
├── playwright.config.ts
└── tests/
    └── e2e/
        └── dashboard.spec.ts
```

## Running locally

Install the frontend dependencies and Chromium:

```bash
cd frontend
npm ci
npx playwright install --with-deps chromium
```

The Playwright configuration does not start a web server. The frontend must
already be running at the default target `http://localhost:3000`, built or
started with `NEXT_PUBLIC_API_URL` pointing to the compatible backend. Override
only the frontend target for a live deployment:

```bash
cd frontend
npm run test:e2e

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
