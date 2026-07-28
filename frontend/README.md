# ClimaSentinel Frontend

Next.js 16 and React 19 dashboard for the ClimaSentinel FastAPI service.

## Routes

- `/` — current 48-hour city ranking from `/data/current-scores`
- `/city/[city_id]` — current five-factor city detail
- `/forecast` — beta Day +1/+2/+3 same-vintage rule forecast

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

## Checks

```bash
npm run lint
npm run build
npm run test:e2e
```

Playwright defaults to `http://localhost:3000`. For a deployed target:

```bash
PLAYWRIGHT_TEST_BASE_URL=https://your-staging-frontend.example npm run test:e2e
```

The current E2E is a desktop-Chromium staging smoke test for Paris across all
three forecast horizons. It does not cover every city/page/browser or pin the
backend to an exact commit.

## Deployment

The staging workflow deploys the frontend and backend as separate Railway
services and stamps the frontend with a commit/run marker before E2E. The
repository's Railway production deployment is currently disabled.

See [Frontend Architecture](../docs/9-frontend.md) and
[End-to-End Testing](../docs/13-end-to-end-testing.md) for the current contracts
and limitations.
