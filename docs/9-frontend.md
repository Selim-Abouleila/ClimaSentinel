# 9. Frontend Architecture

**Live dashboard:** [climasentinel.up.railway.app](https://climasentinel.up.railway.app/)

> **Prototype interpretation contract:** “Live” means the URL is reachable; it
> does not certify a production release, a completed ingestion run or complete
> factor coverage. Before interpreting any score, band, timestamp or validation
> label, read [Critical System Limitations](0-critical-limitations.md).

The ClimaSentinel frontend is a Next.js 16 App Router application written in
TypeScript and deployed to Railway. It consumes only the FastAPI contract; it
does not query BigQuery or load MLflow artifacts directly.

## Technology stack

- Next.js 16 and React 19;
- TypeScript API types in `frontend/src/lib/api.ts`;
- Tailwind CSS v4 plus shared design tokens; and
- Playwright for pure availability and backend-health proxy unit tests, local
  Cold UI fixture tests and live staging end-to-end tests.

`NEXT_PUBLIC_API_URL` identifies the backend and is embedded into the
browser-facing bundle at build time. Railway must therefore provide the correct
value before building the frontend. The backend validates forecast responses
with `CityForecastResponse` and validates current, history and city-detail
operational payloads with dedicated Pydantic models. The TypeScript interfaces
in `frontend/src/lib/api.ts` are compile-time only: the browser currently trusts
parsed JSON and does not perform independent runtime-schema validation.

The API types now include optional `cold_in_global_score` on overview/detail,
plus Cold score/status/monitoring/availability/coverage and Tmin/reference/anomaly
on detail. These additions remain optional for the frontend-first rollout:
an omitted field means the older API did not report it, while an explicit null
score means unavailable data. An absent aggregation mode is unknown, not false.
The city-detail catalogue now displays Cold after Heat, with its own score,
status and coverage. Keep dbt aggregation false until
isolated staging activation and deployment checks pass. Implementing the UI
does not enable Cold in live aggregate scores.

## Main dashboard and city detail

The `/` dashboard renders the current operational heuristic score from
`GET /data/current-scores`. `/city/[city_id]` renders the six-factor signal
catalogue from `GET /data/city/{city_id}/scores`, but only factors with complete
required input coverage receive a numeric score. These pages describe the
current operational marts; they must not be interpreted as model-validation
results.

The current-score client no longer hard-codes `limit=10`; it uses the API's
bounded default of 100. The overview renders every returned city card and
derives the monitored-city count and explanatory copy from the response. After
the expanded ingestion and v2 marts are refreshed, the warehouse's configured
spine keeps that operational surface at 20 cities, including the 10
dashboard-only additions, even when some selected-run signals are unavailable.

The underlying mart selects the two UTC dates “today + tomorrow,” not a rolling
48-hour interval. City detail now labels the window “Today / tomorrow (UTC).”
The overview still displays “48-hour” copy, which remains a known product-label
mismatch. Unlike `/forecast`, these pages do not currently render the
beta/validation disclosure.

Operational factors have three explicit availability states. `available`
renders the numeric heuristic score and product band; `unavailable` renders a
neutral em dash plus the reported coverage; `not_monitored` renders “Not monitored / No source
configured.” Neither missing state receives a green Stable label or meter fill.
Detail copy reports available versus monitored factor counts and states that
missing factors are excluded from the overall maximum. A fully covered input
whose rule genuinely evaluates to zero remains `0.0 · Stable`.

The Cold row does not render a temperature-context panel or its selected-date
explanation. Forecast Tmin, monthly normal Tmin, anomaly and `score_date` remain
available in the API and warehouse. An older API payload that omits Cold shows
“Not reported,” without a synthetic zero, Stable band or meter fill.

The reported `cold_in_global_score` mode controls the aggregate explanation and
dominant-factor eligibility:

| API mode | Cold presentation |
|---|---|
| `false` | Display the independent Cold score, while stating that it is excluded from the aggregate. Even a larger Cold score does not become the dominant participating factor. |
| `true` | Identify Cold as participating; an available Cold score can be the dominant factor. |
| Omitted | Explain that participation was not reported. Do not infer a mode from the presence of a Cold score or the number of monitored factors. |

Aggregate availability and coverage copy displays the counts and overall
coverage supplied by the API. If an older payload omits counts, only a reported
mode permits a fallback count of its participating factors; otherwise counts
remain unreported.
This keeps the default five-factor aggregate consistent with the separately
displayed Cold score, rather than counting all six visible rows.

The overview accepts a nullable city-level score. Cities without an available
participating factor are excluded from the network mean, highest-risk selection and spectrum,
but remain visible as Unavailable cards. Tied worst dates resolve to one
deterministic dbt row before the UI receives them; see
[Mart Layer](4-mart-layer.md#mart_city_score_detail_v2-view).

A city can still have a score when only a subset of its monitored factors is
available. Every such scored city card flags its available/monitored count
(for example `1/4 signals available`), and the network-mean card states how many
scored cities have partial signal coverage. The mean itself includes scored
cities only and does not imply that all their monitored factors were available.

Overview and detail responses carry `operational_ingestion_run_id` and
`operational_ingested_at_utc`. Both pages display the selected snapshot time and
switch to a visible stale warning after 36 hours. This is a mitigation, not a
run audit: there is no completed-run manifest yet, so a failed ingestion can
leave the old snapshot selected and an overlapping, in-progress or partially
successful run can appear newest. The timestamp and freshness threshold do not
prove that all expected sources or factors completed.

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
not enter same-vintage forecast features, ML training or serving. Any future
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
visible per-factor labels. They show the factor score/product band or a source-data
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

The availability release uses a deliberate expand-and-contract order:

1. Run `make deploy` to seed `city_signal_monitoring` and create the exact-run
   v2 staging/marts while the unsuffixed legacy marts and old application stay
   live.
2. Deploy the compatibility frontend, which tolerates both the legacy numeric
   payload and explicit v2 availability metadata, with `railway up --detach`;
3. While Railway builds it, gate the v2 mart schemas, all 20 configured
   current/detail city rows, one coherent selected run and a snapshot age no
   greater than 36 hours; then confirm the frontend's exact commit/run marker
   through a bounded no-cache poll.
4. Stamp and queue the backend that reads v2 with `--detach`, then poll the
   frontend's `/api/backend-health` proxy until it reports `healthy` with the
   exact same release ID before running staging E2E.

Both submissions are asynchronous, but the cutovers are intentionally not
parallel: mart readiness and frontend confirmation must both pass before the
backend is submitted. Each primary release poll has a strict 600-second
deadline, caps individual requests at 10 seconds and waits no more than 10
seconds between attempts. The E2E job reconfirms both identities after its job
boundary.

The unsuffixed marts remain temporary rollback compatibility and do not expose
the v2 column contract.

Cold release verification remains a separate gate: keep
`cold_in_global_score: false` on the shared warehouse until staging datasets
are isolated and the Cold schema/activation checks are ready. Promote through
PR `dev` → `staging`, deploy and verify the warehouse, API and UI there, and
only then open PR `staging` → `main`. Local fixture browser success does not
establish that the staging release is deployed or that production is ready;
the production Railway deployment workflow remains disabled.

The pure unit suite checks legacy compatibility, explicit v2 false precedence,
measured zero, unavailable factors and aggregation with partial/all-unavailable
inputs in `signal-availability.spec.ts`. It also verifies the health proxy's
no-cache pass-through and unreachable-backend `502` response in
`backend-health-route.spec.ts`. It runs in PR CI with `npm run test:unit` and
does not contact a browser or live service.

`npm run test:cold-ui` runs a separate local browser suite against deterministic
Cold fixtures. It checks the rendered Cold score/status/coverage, valid zero,
the absence of the temperature-context panel, missing/partial/unmonitored
states, older payloads and both reported aggregation
modes. See [End-to-End Testing](13-end-to-end-testing.md#local-cold-ui-fixture-suite)
for its scope and execution. It does not replace live BigQuery or staging
release verification and is separate from `npm run test:e2e`.

The staging Playwright smoke test verifies the
`forecast_rules_baseline` API contract for Paris across all three horizons and
checks the global beta disclosure and freezes the selector at the original 10
choices. It also opens Stockholm's operational detail and asserts that its
unmonitored River factor contains neither `Stable` nor `0.0`. It does not verify
visible per-factor validation labels, the other nine forecast cities, the full
20-city overview or an injected temporary source outage. The deployment gate,
rather than Playwright assertions, pins the backend to the exact commit/run
release. A rejected challenger is not required to be deployed.
