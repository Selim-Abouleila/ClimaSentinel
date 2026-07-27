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

`NEXT_PUBLIC_API_URL` identifies the backend. The forecast response is validated
by the backend's typed `CityForecastResponse` contract, including nullable
unavailable factors. The operational current-score and city-detail endpoints
return BigQuery rows directly and do not provide the same typed response-model
validation.

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

The page gives a prominent global beta disclosure and validation-scope note:

- all five factors are deterministic indicators calculated from the selected
  horizon's same-vintage forecasts;
- Heat is described as having only limited backtest evidence;
- Rain is described as having performed poorly in backtests;
- Wind, Air Quality and River are described as lacking observed validation;
- a source gap is displayed as unavailable, not as a green zero-risk value; and
- no component or aggregate model-confidence interval is displayed.

The API carries `method`, `validation_status`, `provenance` and `method_reason`
for every factor, but the current factor cards do **not** render those values as
visible per-factor labels. They show the factor score/risk band or a source-data
unavailable state. `method` is present only as a non-visible
`data-forecast-method` attribute. Product copy must therefore not claim that the
current UI presents detailed provenance on every card.

The current global note is:

> Heat has limited backtest evidence; Rain performed poorly in backtests; Wind,
> air quality and river lack observed validation. Scores are point estimates
> without confidence bands. Missing inputs are marked unavailable.

## Loading and failure states

The forecast page distinguishes among initial selection, loading, a successful
rule-baseline result and a connection/data error. A backend failure produces a
retryable “Forecast unavailable” state. Individual optional-source gaps can still
produce a successful response; only the affected rule cards are unavailable.

## Deployment compatibility

The API exposes method, availability and validation fields and keeps all model
uncertainty nullable. Backend and frontend should therefore be promoted as one
release. The staging Playwright smoke test verifies the
`forecast_rules_baseline` API contract for Paris across all three horizons and
checks the global beta disclosure. It does not verify visible per-factor
validation labels, the other nine cities, the overview or city-detail pages, or
an exact backend commit marker. A rejected challenger is not required to be
deployed.
