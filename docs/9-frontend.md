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

`NEXT_PUBLIC_API_URL` identifies the backend and is embedded into the
browser-facing bundle at build time. Railway must therefore provide the correct
value before building the frontend. The backend validates forecast responses
with its typed `CityForecastResponse` contract, including nullable unavailable
factors. The TypeScript interface in `frontend/src/lib/api.ts` is compile-time
only: the browser currently trusts parsed JSON and does not perform an
independent runtime-schema validation. The operational current-score and
city-detail endpoints return BigQuery rows directly and do not provide the same
typed backend response model.

## Main dashboard and city detail

The `/` dashboard renders current operational risk from
`GET /data/current-scores`. `/city/[city_id]` renders the five operational
factor scores from `GET /data/city/{city_id}/scores`. These pages describe the
current operational marts; they must not be interpreted as model-validation
results.

The current-score client no longer hard-codes `limit=10`; it uses the API's
bounded default of 100. The overview renders every returned city card and
derives the monitored-city count and explanatory copy from the response. After
the expanded ingestion and marts are refreshed, that operational surface
contains 20 cities, including the 10 dashboard-only additions.

The underlying mart selects the two UTC dates “today + tomorrow,” not a rolling
48-hour interval. The current overview and city page still display “48-hour”
copy, which is a known product-label mismatch. Both pages also use legacy marts
that can mask some missing inputs; unlike `/forecast`, they do not currently
render the beta/validation disclosure.

On the city page, tied maximum dates are not resolved deterministically by the
current detail-mart SQL, and separately aggregated factor fields can come from
different tied dates. The frontend renders that payload without detecting the
tie; see [Mart Layer](4-mart-layer.md#mart_city_score_detail-view).

The overview converts any API failure into an empty array and shows the same
empty state as a legitimate zero-row response. The city client converts a
`404`, any other non-success response and a network failure to `null`, after
which the route renders Next.js's not-found page. Those pages therefore do not
currently distinguish “no data/unknown city” from an upstream outage.

## Three-day forecast page

`/forecast` lets the user select a city and one genuine Day +1, Day +2 or Day +3
horizon. A selection calls
`GET /data/city/{city_id}/forecast?horizon_days={1|2|3}`; the client never creates
a shorter horizon by reusing Day +3 output.

The forecast selector remains deliberately hard-coded to the original 10-city
contract: Paris, London, Madrid, Berlin, Rome, Amsterdam, Athens, Warsaw,
Lisbon and Stockholm. Vienna, Brussels, Copenhagen, Dublin, Oslo, Helsinki,
Prague, Budapest, Zurich and Bucharest appear on the operational dashboard but
are absent from the forecast selector and `forecast_city_allowlist.csv`; they do
not enter point-in-time forecast features, ML training or serving. Any future
forecast expansion requires an explicit coordinated allowlist, backend and
frontend contract change rather than following operational registry growth.

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

`estimated_total_tipping_score` is the maximum available factor score, not an
additive total. “Current baseline” is calculated from the forecast-origin day's
same-vintage inputs and is not an observed climate-impact baseline. An
unavailable factor displays generic “Source data unavailable” copy; the
specific API `unavailable_reason` is available only through the card's native
title tooltip.

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
checks the global beta disclosure and freezes the selector at the original 10
choices. It does not verify visible per-factor validation labels, the other nine
forecast cities, the 20-city overview or city-detail pages, or an exact backend
commit marker. A rejected challenger is not required to be deployed.
