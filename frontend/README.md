# ClimaSentinel Frontend

Next.js 16 and React 19 dashboard for the ClimaSentinel FastAPI service.

## Routes

- `/` — city ranking from `/data/current-scores` over today and tomorrow UTC
- `/city/[city_id]` — five-factor catalogue with nullable scores and explicit
  monitoring, availability and coverage over those two UTC dates
- `/forecast` — beta Day +1/+2/+3 same-vintage rule forecast

The overview and city-detail routes consume the 20-city operational surface.
Their backend routes read `mart_city_score_current_v2` and
`mart_city_score_detail_v2`; the warehouse spine keeps all 20 configured cities
visible while individual unavailable signals remain NULL.

The forecast route intentionally remains restricted to the original 10-city
allowlist; operational registry growth does not automatically change its
selector, feature, training or serving scope.

The overview and city UI still use legacy “48-hour” copy, but their dbt marts
select two UTC calendar dates rather than a rolling 48-hour interval. Tied
dates resolve to one deterministic row. Unavailable and unmonitored factors
render neutrally with no numeric score or Stable label; a measured, complete
zero remains numeric. See [Frontend Architecture](../docs/9-frontend.md).

Both pages display the exact selected operational snapshot timestamp and mark
it stale after 36 hours. Scored city cards always identify partial factor
coverage, and the network mean notes how many included scored cities are
partial. The timestamp is a visibility aid rather than a run-completion proof:
the ingestion pipeline has no durable run manifest yet, so a failed run can
leave an old snapshot selected and an overlapping/in-progress run can briefly
appear newest.

The forecast is experimental. It displays a prominent beta badge and a global
note explaining that Heat has limited backtest evidence, Rain performed poorly
in backtests, and Wind, air quality and river lack observed validation. Factor
cards do not currently show the API's detailed validation/provenance fields.

## Local development

Use Node.js 20 and start a compatible backend on port `8000`.

```bash
npm ci
NEXT_PUBLIC_API_URL=http://127.0.0.1:8000 npm run dev
```

Open `http://localhost:3000`.

`NEXT_PUBLIC_API_URL` must be set before a production build so both server-side
dashboard requests and the browser-side forecast page target the intended API.
The TypeScript interfaces are compile-time types; the browser does not currently
perform runtime schema validation on API JSON.

## Checks

```bash
npm run lint
npm run build
npm run test:unit
npm run test:e2e
```

Lint, build and `test:unit` are self-contained. The unit suite uses Playwright's
test runner for pure TypeScript availability, aggregation and 36-hour freshness
cases; it does not open a browser page. The E2E command does not start the
frontend or backend, so both must already be running and compatible. It defaults
to `http://localhost:3000`. For a deployed frontend target:

```bash
PLAYWRIGHT_TEST_BASE_URL=https://your-staging-frontend.example npm run test:e2e
```

The current E2E is a desktop-Chromium staging smoke test for Paris across all
three forecast horizons, asserts the exact 10-city forecast selector, and
checks Stockholm's deterministic `River / Flood · Not monitored` detail state.
It does not cover the complete 20-city surface, every browser, a temporary
source outage, or an exact backend commit, and it does not run dbt tests or
prove mart freshness.

## Deployment

The availability rollout uses this order:

1. `make deploy` creates/tests the v2 data relations while unsuffixed legacy
   marts and the old application remain live;
2. staging deploys the compatibility frontend and confirms its exact
   commit/run marker;
3. staging gates the v2 schemas, exact 20-city current/detail coverage, one
   selected run and a snapshot age no greater than 36 hours;
4. staging deploys the v2 backend and runs E2E.

The unsuffixed marts remain temporary legacy rollback compatibility and should
not be treated as having v2 availability columns. The repository's Railway
production deployment is currently disabled.
`NEXT_PUBLIC_API_URL` is supplied by Railway configuration rather than the
workflow file and must exist before the staging frontend build. The release
marker identifies the frontend only.

This Railway application deployment does not rebuild or execute the GCP Cloud
Run ingestion job and does not refresh or test the expanded BigQuery/dbt data
plane. The v2 operational relations must already be present from a successful
`make deploy` run; the staging readiness query validates but does not create or
test them.

See [Frontend Architecture](../docs/9-frontend.md) and
[End-to-End Testing](../docs/13-end-to-end-testing.md) for the current contracts
and limitations.
