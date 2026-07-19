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

- Heat and Rain are learned predictions trained against realized ERA5 outcomes;
- Wind, Air Quality and River are deterministic indicators calculated from the
  selected horizon's same-vintage forecasts;
- a source gap is displayed as unavailable, not as a green zero-risk value; and
- model-spread bounds appear only for learned Heat/Rain outputs.

The tree-spread display is explicitly described as uncalibrated model
disagreement, not as a guaranteed 95% confidence interval. Rule-derived cards do
not display a confidence interval. If a rule-derived factor is the total's
primary driver, the total interval is also omitted.

The following disclaimer remains visible until observed gust, AQ and river
outcomes are ingested and validated:

> Model validation currently covers heat and rainfall only. Wind, air-quality
> and river-risk values are forecast-based indicators and are not yet validated
> against observed outcomes.

## Loading and failure states

The forecast page distinguishes among initial selection, loading, a successful
hybrid result and a connection/model error. A 503 from the backend produces a
retryable “Forecast unavailable” state. It does not substitute a production
model failure with fabricated scores. Individual optional-source gaps can still
produce a successful response; only the affected rule cards are unavailable.

## Deployment compatibility

The hybrid API adds method, availability and validation fields and makes rule
uncertainty nullable. Backend and frontend should therefore be promoted as one
release. The staging Playwright test verifies the concrete promoted model
version and the distinction between learned and rule-derived components before
production promotion.
