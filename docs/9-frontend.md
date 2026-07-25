# 9. Frontend Architecture

**Live dashboard:** [climasentinel.up.railway.app](https://climasentinel.up.railway.app/)

The ClimaSentinel frontend is a Next.js 16 App Router application written in
TypeScript and deployed to Railway. It consumes only the FastAPI contract; it
does not query BigQuery or load MLflow artifacts directly.

## Technology stack

- Next.js 16 and React 19;
- TypeScript API types in `frontend/src/lib/api.ts`;
- Tailwind CSS v4 plus shared design tokens; and
- Playwright for live staging end-to-end tests.

`NEXT_PUBLIC_API_URL` identifies the backend. All score values are sanitized by
the API before display, while nullable unavailable factors remain nullable in
the client contract.

## Main dashboard and city detail

The `/` dashboard renders current operational risk from
`GET /data/current-scores`. `/city/[city_id]` renders the five operational
factor scores from `GET /data/city/{city_id}/scores`. These pages describe the
current operational marts; they must not be interpreted as model-validation
results.

## Three-day forecast page

`/forecast` lets the user select a city and one genuine Day +1, Day +2 or Day +3
horizon. A selection calls
`GET /data/city/{city_id}/forecast?horizon_days={1|2|3}`; the client never creates
a shorter horizon by reusing Day +3 output.

The result page renders method and validation provenance per factor:

- all five factors are deterministic indicators calculated from the selected
  horizon's same-vintage forecasts;
- Heat is labelled as having only a limited backtest against realized ERA5;
- Rain is labelled as ERA5-backtested with insufficient predictive skill;
- Wind, Air Quality and River are labelled as lacking observed-label validation;
- a source gap is displayed as unavailable, not as a green zero-risk value; and
- no component or aggregate model-confidence interval is displayed.

The frontend does not turn formula outputs into pseudo-confidence bounds. API
interval fields are required to be null and the page explicitly states that no
model confidence interval is claimed.

The following disclaimer remains visible until observed gust, AQ and river
outcomes are ingested and validated:

> Heat uses a same-vintage forecast rule with a limited ERA5 backtest. Rain was
> backtested against realized ERA5 but showed insufficient predictive skill.
> Wind, air-quality and river-risk still lack observed-label validation.

## Loading and failure states

The forecast page distinguishes among initial selection, loading, a successful
rule-baseline result and a connection/data error. A backend failure produces a
retryable “Forecast unavailable” state. Individual optional-source gaps can still
produce a successful response; only the affected rule cards are unavailable.

## Deployment compatibility

The API exposes method, availability and validation fields and keeps all model
uncertainty nullable. Backend and frontend should therefore be promoted as one
release. The staging Playwright test verifies the `forecast_rules_baseline`
contract across all three horizons; it does not require a rejected challenger
to be deployed.
