import Link from 'next/link';
import { fetchCurrentScores } from '@/lib/api';
import {
  getSnapshotFreshness,
  hasCurrentScore,
  hasPartialFactorCoverage,
  meanCurrentScore,
  scoredCurrentCities,
} from '@/lib/signal-availability';

type RiskTone = 'stable' | 'monitoring' | 'tipping' | 'critical';

interface RiskBand {
  label: string;
  tone: RiskTone;
  range: string;
}

const RISK_BANDS: RiskBand[] = [
  { label: 'Stable', tone: 'stable', range: '0–30' },
  { label: 'Monitoring', tone: 'monitoring', range: '31–60' },
  { label: 'Tipping', tone: 'tipping', range: '61–80' },
  { label: 'Critical', tone: 'critical', range: '81–100' },
];

function getRiskBand(score: number): RiskBand {
  if (score >= 81) return RISK_BANDS[3];
  if (score >= 61) return RISK_BANDS[2];
  if (score >= 31) return RISK_BANDS[1];
  return RISK_BANDS[0];
}

function formatCity(cityId: string) {
  const [city = cityId, country = ''] = cityId.split('_');
  const cityName = city.charAt(0).toUpperCase() + city.slice(1);
  return {
    cityName,
    countryCode: country.toUpperCase(),
    displayName: country ? `${cityName}, ${country.toUpperCase()}` : cityName,
    shortCode: city.slice(0, 3).toUpperCase(),
  };
}

export default async function Dashboard() {
  const cityData = await fetchCurrentScores();

  const monitoredCities = cityData.length;
  const scoredCities = scoredCurrentCities(cityData);
  const unavailableCityCount = monitoredCities - scoredCities.length;
  const partialCoverageCityCount = cityData.filter(hasPartialFactorCoverage).length;
  const cityNoun = monitoredCities === 1 ? 'city' : 'cities';
  const metropolitanAreaNoun = monitoredCities === 1 ? 'area' : 'areas';
  const avgRisk = meanCurrentScore(cityData);

  const highestRiskCity = scoredCities.length > 0
    ? scoredCities.reduce((prev, current) => (
        prev.current_tipping_score >= current.current_tipping_score ? prev : current
      ))
    : null;
  const highestRiskCities = highestRiskCity
    ? scoredCities.filter((city) => city.current_tipping_score === highestRiskCity.current_tipping_score)
    : [];
  const highestRiskLabel = highestRiskCities.length > 1
    ? highestRiskCities.map((city) => formatCity(city.city_id).cityName).join(' & ')
    : highestRiskCity
      ? formatCity(highestRiskCity.city_id).displayName
      : '—';
  const averageBand = avgRisk === null ? null : getRiskBand(avgRisk);
  const highestBand = highestRiskCity ? getRiskBand(highestRiskCity.current_tipping_score) : null;
  const snapshot = getSnapshotFreshness(cityData[0]?.operational_ingested_at_utc);
  const snapshotLabel = snapshot?.ingestedAt.toLocaleString('en-GB', {
    day: '2-digit',
    month: 'short',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
    timeZone: 'UTC',
  });

  return (
    <main className="dashboard-shell">
      <div className="dashboard-container">
        <header className="dashboard-hero">
          <div className="dashboard-eyebrow">
            <span className="dashboard-eyebrow__dot" aria-hidden="true" />
            Europe · {monitoredCities} {cityNoun} · 48-hour outlook
          </div>
          <h1>European climate risk monitor</h1>
          <p>
            {monitoredCities > 0
              ? `Current climate stress signals and their dominant drivers across ${monitoredCities} monitored metropolitan ${metropolitanAreaNoun}.`
              : 'Current climate stress signals and their dominant drivers across the monitored European metropolitan network.'}
          </p>
        </header>

        {snapshot && (
          <div
            className={`dashboard-freshness ${snapshot.stale ? 'is-stale' : ''}`}
            role="status"
            aria-label={snapshot.stale ? 'Data snapshot is stale' : 'Selected data snapshot'}
          >
            <span>{snapshot.stale ? 'Stale data snapshot' : 'Selected data snapshot'}</span>
            <time dateTime={snapshot.ingestedAt.toISOString()}>{snapshotLabel} UTC</time>
            <small>
              {snapshot.stale
                ? 'The scheduled daily ingestion is overdue; interpret scores cautiously.'
                : 'One exact ingestion run is used across all available signals.'}
            </small>
          </div>
        )}

        {cityData.length === 0 ? (
          <div className="dashboard-empty-state" role="status">
            <span className="dashboard-empty-state__indicator" aria-hidden="true" />
            <h2>Climate signals unavailable</h2>
            <p>The monitoring API has not returned a current 48-hour city outlook.</p>
          </div>
        ) : (
          <>
            <section className="summary-grid" aria-label="Network summary">
              <article className="summary-card">
                <div className="summary-card__topline">
                  <span className="summary-card__label">Cities monitored</span>
                  <span className="summary-card__index">01</span>
                </div>
                <div className="summary-card__value">{monitoredCities}</div>
                <p>European metropolitan areas</p>
              </article>

              <article className={`summary-card ${averageBand ? `risk-${averageBand.tone}` : 'signal-unavailable'}`}>
                <div className="summary-card__topline">
                  <span className="summary-card__label">Mean network score</span>
                  <span className="summary-card__index">02</span>
                </div>
                <div className="summary-card__metric">
                  <span className="summary-card__value">{avgRisk === null ? '—' : avgRisk.toFixed(1)}</span>
                  {avgRisk !== null && <span className="summary-card__unit">/ 100</span>}
                </div>
                <div className="summary-card__status">
                  <span className="risk-dot" aria-hidden="true" />
                  {averageBand?.label ?? 'Unavailable'}
                </div>
                {avgRisk !== null && (unavailableCityCount > 0 || partialCoverageCityCount > 0) && (
                  <p>
                    {unavailableCityCount > 0
                      ? `${unavailableCityCount} ${unavailableCityCount === 1 ? 'city' : 'cities'} excluded without a score`
                      : ''}
                    {unavailableCityCount > 0 && partialCoverageCityCount > 0 ? ' · ' : ''}
                    {partialCoverageCityCount > 0
                      ? `${partialCoverageCityCount} scored ${partialCoverageCityCount === 1 ? 'city has' : 'cities have'} partial signal coverage`
                      : ''}
                  </p>
                )}
              </article>

              <article className={`summary-card ${highestBand ? `risk-${highestBand.tone}` : 'signal-unavailable'}`}>
                <div className="summary-card__topline">
                  <span className="summary-card__label">
                    Highest-risk {highestRiskCities.length > 1 ? 'cities' : 'city'}
                  </span>
                  <span className="summary-card__index">03</span>
                </div>
                <div className="summary-card__city">
                  {highestRiskLabel}
                </div>
                <p>
                  {highestRiskCity ? `${highestRiskCity.current_tipping_score.toFixed(1)} / 100 · ${highestBand?.label}` : 'Unavailable'}
                </p>
              </article>
            </section>

            <section className="risk-spectrum-panel" aria-labelledby="risk-spectrum-title">
              <div className="risk-spectrum-panel__header">
                <div>
                  <span className="section-kicker">Network distribution</span>
                  <h2 id="risk-spectrum-title">Risk spectrum</h2>
                </div>
                <p>Worst-case city score in the current 48-hour window</p>
              </div>
              <div className="risk-spectrum" aria-label="City scores distributed on a scale from zero to one hundred">
                <div className="risk-spectrum__plot">
                  <div className="risk-spectrum__bands" aria-hidden="true">
                    <span className="risk-spectrum__band risk-stable" />
                    <span className="risk-spectrum__band risk-monitoring" />
                    <span className="risk-spectrum__band risk-tipping" />
                    <span className="risk-spectrum__band risk-critical" />
                  </div>
                  {scoredCities.map((city, index) => {
                    const cityName = formatCity(city.city_id);
                    const band = getRiskBand(city.current_tipping_score);
                    const safePosition = Math.min(98, Math.max(2, city.current_tipping_score));
                    return (
                      <Link
                        key={city.city_id}
                        href={`/city/${city.city_id}`}
                        className={`risk-spectrum__marker risk-${band.tone} risk-spectrum__marker--lane-${index % 5}`}
                        style={{ left: `${safePosition}%` }}
                        title={`${cityName.displayName}: ${city.current_tipping_score.toFixed(1)} / 100`}
                        aria-label={`View ${cityName.displayName}, score ${city.current_tipping_score.toFixed(1)} out of 100`}
                      >
                        <span>{cityName.shortCode}</span>
                        <i aria-hidden="true" />
                      </Link>
                    );
                  })}
                </div>
                <div className="risk-spectrum__axis" aria-hidden="true">
                  <span>0</span>
                  <span>31</span>
                  <span>61</span>
                  <span>81</span>
                  <span>100</span>
                </div>
                {unavailableCityCount > 0 && (
                  <p className="risk-spectrum__availability-note">
                    {unavailableCityCount} {unavailableCityCount === 1 ? 'city is' : 'cities are'} unavailable and excluded from the score distribution.
                  </p>
                )}
              </div>
            </section>

            <section className="city-profile" aria-labelledby="city-profile-title">
              <div className="city-profile__header">
                <div>
                  <span className="section-kicker">Operational ranking</span>
                  <h2 id="city-profile-title">City risk profile</h2>
                  <p>Ranked by the highest signal in the current 48-hour window.</p>
                </div>
                <div className="risk-legend" aria-label="Risk thresholds">
                  {RISK_BANDS.map((band) => (
                    <span key={band.tone} className={`risk-legend__item risk-${band.tone}`}>
                      <i className="risk-dot" aria-hidden="true" />
                      <span>{band.label}</span>
                      <small>{band.range}</small>
                    </span>
                  ))}
                </div>
              </div>

              <div className="city-grid">
                {cityData.map((city, index) => {
                  const hasScore = hasCurrentScore(city);
                  const band = hasScore ? getRiskBand(city.current_tipping_score) : null;
                  const cityName = formatCity(city.city_id);
                  const rank = hasScore ? city.rank ?? index + 1 : null;

                  return (
                    <Link
                      key={city.city_id}
                      href={`/city/${city.city_id}`}
                      className={`city-risk-card ${band ? `risk-${band.tone}` : 'signal-unavailable'}`}
                      aria-label={`View ${cityName.displayName} climate risk details${hasScore ? '' : ', current score unavailable'}`}
                    >
                      <div className="city-risk-card__header">
                        <span className="city-risk-card__rank">{rank === null ? '—' : `#${String(rank).padStart(2, '0')}`}</span>
                        <span className="city-risk-card__status">
                          <i className="risk-dot" aria-hidden="true" />
                          {band?.label ?? 'Unavailable'}
                        </span>
                      </div>

                      <div className="city-risk-card__title-row">
                        <h3>{cityName.cityName}</h3>
                        <span>{cityName.countryCode}</span>
                      </div>

                      <div className="city-risk-card__score-row">
                        <strong>{hasScore ? city.current_tipping_score.toFixed(1) : '—'}</strong>
                        {hasScore && <span>/ 100</span>}
                      </div>

                      <div
                        className="city-risk-card__meter"
                        role="img"
                        aria-label={hasScore
                          ? `${cityName.displayName}: ${city.current_tipping_score.toFixed(1)} out of 100`
                          : `${cityName.displayName}: current score unavailable`}
                      >
                        {hasScore && <span style={{ width: `${Math.min(100, Math.max(0, city.current_tipping_score))}%` }} />}
                      </div>

                      {hasPartialFactorCoverage(city) && (
                        <div className="city-risk-card__coverage" role="status">
                          Partial coverage · {city.available_factor_count} / {city.monitored_factor_count} signals available
                        </div>
                      )}

                      <div className="city-risk-card__footer">
                        <span>{hasScore ? 'Dominant driver' : 'Signal availability'}</span>
                        <strong>
                          {hasScore
                            ? city.current_primary_driver || 'Unknown'
                            : typeof city.available_factor_count === 'number'
                                && typeof city.monitored_factor_count === 'number'
                              ? `${city.available_factor_count} / ${city.monitored_factor_count} available`
                              : 'Current score unavailable'}
                        </strong>
                        <svg viewBox="0 0 16 16" fill="none" aria-hidden="true">
                          <path d="M3 8h9M8.5 4.5 12 8l-3.5 3.5" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" />
                        </svg>
                      </div>
                    </Link>
                  );
                })}
              </div>

              <footer className="dashboard-data-note">
                <span>Signal catalogue</span>
                Heat · Wind · Rain · Air quality · River discharge · Availability varies by city
              </footer>
            </section>
          </>
        )}
      </div>
    </main>
  );
}
