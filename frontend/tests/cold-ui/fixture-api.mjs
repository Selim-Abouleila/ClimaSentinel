import { createServer } from 'node:http';

// The city page fetches on the Next server, so browser route interception
// cannot supply these responses. Each URL has immutable data for parallel tests.
const originalFactors = ['heat', 'wind', 'rain', 'air', 'river'];
const originalScores = [10, 20, 5, 0, 0];

function detail(cityId) {
  const row = {
    operational_ingestion_run_id: 'cold-ui-fixture',
    operational_ingested_at_utc: '2026-09-15T06:00:00Z',
    city_id: cityId,
    score_date: '2026-09-15',
    current_tipping_score: 20,
    current_primary_driver: 'Wind',
    current_score_available: true,
    cold_in_global_score: false,
    monitored_factor_count: 5,
    available_factor_count: 5,
    overall_coverage: 1,
    cold_score: 100,
    cold_status: 'available',
    cold_monitored: true,
    cold_available: true,
    cold_coverage: 1,
    temperature_2m_min: -20,
    normal_temperature_2m_min: 0,
    cold_anomaly_c: 20,
  };
  originalFactors.forEach((factor, index) => Object.assign(row, {
    [`${factor}_score`]: originalScores[index],
    [`${factor}_status`]: 'available',
    [`${factor}_monitored`]: true,
    [`${factor}_available`]: true,
    [`${factor}_coverage`]: 1,
  }));
  return row;
}

const fixtures = new Map();
function scenario(cityId, changes = {}) {
  const row = { ...detail(cityId), ...changes };
  fixtures.set(cityId, row);
  return row;
}

scenario('zero_fr', { cold_score: 0, temperature_2m_min: 0, cold_anomaly_c: 0 });
scenario('smallanomaly_fr', {
  cold_score: 0.1, temperature_2m_min: -0.01, cold_anomaly_c: 0.01,
});
scenario('partial_fr', {
  operational_ingested_at_utc: '2026-09-14T06:00:00Z',
  cold_score: null, cold_status: 'unavailable', cold_available: false,
  cold_coverage: 0.958, temperature_2m_min: -5, cold_anomaly_c: null,
});
scenario('unmonitored_fr', {
  cold_score: null, cold_status: 'not_monitored', cold_monitored: false,
  cold_available: false, cold_coverage: null,
});
scenario('excluded_fr');
scenario('included_fr', {
  cold_in_global_score: true, current_tipping_score: 100,
  current_primary_driver: 'Cold', monitored_factor_count: 6,
  available_factor_count: 6,
});
const legacy = scenario('legacy_fr');
for (const key of ['cold_in_global_score', 'cold_score', 'cold_status', 'cold_monitored',
  'cold_available', 'cold_coverage', 'temperature_2m_min', 'normal_temperature_2m_min',
  'cold_anomaly_c']) delete legacy[key];
const unknown = scenario('unknown_fr');
delete unknown.cold_in_global_score;
const unknownCounts = scenario('unknowncounts_fr');
for (const key of ['cold_in_global_score', 'monitored_factor_count', 'available_factor_count']) {
  delete unknownCounts[key];
}
scenario('contradictory_fr', { current_primary_driver: 'Cold' });
const unavailableGlobal = scenario('unavailableglobal_fr', {
  current_tipping_score: null, current_primary_driver: 'Unavailable',
  current_score_available: false, available_factor_count: 0, overall_coverage: 0,
});
for (const factor of originalFactors) Object.assign(unavailableGlobal, {
  [`${factor}_score`]: null, [`${factor}_status`]: 'unavailable',
  [`${factor}_available`]: false, [`${factor}_coverage`]: 0,
});

const server = createServer((request, response) => {
  const url = new URL(request.url, 'http://127.0.0.1:4319');
  const match = /^\/data\/city\/([^/]+)\/scores$/.exec(url.pathname);
  const payload = url.pathname === '/health'
    ? { status: 'ok', fixture: 'cold-ui' }
    : match ? fixtures.get(decodeURIComponent(match[1])) : undefined;
  response.writeHead(payload ? 200 : 404, {
    'Content-Type': 'application/json',
    'Cache-Control': 'no-store',
  });
  response.end(JSON.stringify(payload ?? { detail: 'Unknown Cold UI fixture' }));
});

server.listen(4319, '127.0.0.1');
for (const signal of ['SIGTERM', 'SIGINT']) {
  process.on(signal, () => {
    server.close(() => process.exit(0));
    server.closeAllConnections();
  });
}
