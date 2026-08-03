# 13. End-to-End Testing

Playwright provides live staging smoke paths through the forecast frontend and
one operational city-detail missingness state. MLflow challengers are evaluated
separately. Unit/dbt contract tests remain responsible for formula boundaries,
partial coverage, measured-zero semantics, the 36-hour freshness threshold and
failure branches. This test increases confidence in the
deployed contracts, but it is not a complete release, browser, city or
failure-mode suite.

## What the staging test verifies

`frontend/tests/e2e/dashboard.spec.ts` first opens `/forecast`, selects Paris
and exercises each genuine Day +1, Day +2 and Day +3 selector in desktop
Chromium. That path verifies that:

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

A second path opens `/city/stockholm_se`. Because Stockholm is deterministically
`river_monitored=false`, it asserts that the River/Flood row says “Not
monitored” and “No source configured,” contains an em dash, and contains neither
`Stable` nor `0.0`. It also verifies the explanation that missing signals are
excluded from the overall score. This covers configuration absence; it does not
inject a temporary monitored-source outage.

## Staging workflow order

The live E2E job runs only from `.github/workflows/ci-staging.yml` after:

1. the full `backend/tests/` pytest suite passes;
2. a schema-v3 `ClimaSentinel_HeatRainForecaster` challenger is trained and
   registered;
3. the exact challenger is evaluated; quality rejection is recorded without
   moving `champion`, while operational/contract errors still fail the job;
4. the compatibility frontend is stamped and deployed, and CI confirms its
   exact `${GITHUB_SHA}-${GITHUB_RUN_ID}` release marker;
5. a BigQuery readiness gate verifies the required columns on all four v2
   marts, exact monitoring-seed and 20-city current/detail membership, one
   coherent selected run, and a snapshot age no greater than 36 hours;
6. only then is the v2 backend deployed; and
7. Playwright reconfirms the frontend marker and validates the live Paris and
   Stockholm paths.

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

The workflow's first test step is the backend pytest suite. Neither that step,
the readiness query nor Playwright runs `dbt build/test` or verifies all
warehouse lineage contracts. PR CI separately performs a credential-free
`dbt parse`. The staging gate assumes `make deploy` already created/tested v2
and proves schema/city/run/age readiness at cutover, not ongoing mart freshness
after deployment.

It also does not execute the GCP ingestion job or render/assert all 20 cities in
the operational overview. The readiness gate does require all 20 configured
IDs in current/detail v2, while the registry, 240-row normals, 20-row monitoring
seed and frozen forecast allowlist are validated by PR CI and built separately
by `make deploy`.

## Deliberate scope limits

The current smoke test does not cover:

- the other nine forecast-eligible cities;
- the complete 20-city operational coverage or `/` overview;
- operational detail pages other than Stockholm;
- Firefox, WebKit, mobile layouts or accessibility conformance;
- a deliberately interrupted monitored AQ/River feed or other injected backend failure;
- authentication, rate limiting, continuous dependency readiness or monitoring;
- exact backend commit identity;
- authenticated dbt builds/tests, complete lineage or live-mart freshness;
- a completed-run manifest or overlapping/in-progress ingestion behavior;
- exact rendered score values against the corresponding API fields; or
- screenshot-based visual regression.

These are coverage gaps, not claims that those paths are broken.

## Directory structure

```text
frontend/
├── playwright.config.ts
├── playwright.unit.config.ts
└── tests/
    ├── e2e/
    │   └── dashboard.spec.ts
    └── unit/
        └── signal-availability.spec.ts
```

## Running locally

Install the frontend dependencies and Chromium:

```bash
cd frontend
npm ci
npm run test:unit
npx playwright install --with-deps chromium
```

The unit command runs pure TypeScript availability/aggregation cases without a
browser page or live server. It covers legacy numeric compatibility, explicit
v2 availability precedence, partial/all-unavailable aggregation, measured zero,
unavailable AQ, unmonitored River and the exact 36-hour stale threshold.

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
