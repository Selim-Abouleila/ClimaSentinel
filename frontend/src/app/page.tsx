import Link from 'next/link';
import { fetchCurrentScores } from '@/lib/api';

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
  const cityNoun = monitoredCities === 1 ? 'city' : 'cities';
  const metropolitanAreaNoun = monitoredCities === 1 ? 'area' : 'areas';
  const avgRisk = monitoredCities > 0
    ? cityData.reduce((acc, curr) => acc + curr.current_tipping_score, 0) / monitoredCities
    : 0;

  const highestRiskCity = monitoredCities > 0
    ? cityData.reduce((prev, current) => (
        prev.current_tipping_score >= current.current_tipping_score ? prev : current
      ))
    : null;
  const highestRiskCities = highestRiskCity
    ? cityData.filter((city) => city.current_tipping_score === highestRiskCity.current_tipping_score)
    : [];
  const highestRiskLabel = highestRiskCities.length > 1
    ? highestRiskCities.map((city) => formatCity(city.city_id).cityName).join(' & ')
    : highestRiskCity
      ? formatCity(highestRiskCity.city_id).displayName
      : '—';
  const averageBand = getRiskBand(avgRisk);
  const highestBand = highestRiskCity ? getRiskBand(highestRiskCity.current_tipping_score) : null;

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

              <article className={`summary-card risk-${averageBand.tone}`}>
                <div className="summary-card__topline">
                  <span className="summary-card__label">Mean network score</span>
                  <span className="summary-card__index">02</span>
                </div>
                <div className="summary-card__metric">
                  <span className="summary-card__value">{avgRisk.toFixed(1)}</span>
                  <span className="summary-card__unit">/ 100</span>
                </div>
                <div className="summary-card__status">
                  <span className="risk-dot" aria-hidden="true" />
                  {averageBand.label}
                </div>
              </article>

              <article className={`summary-card ${highestBand ? `risk-${highestBand.tone}` : ''}`}>
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
                  {highestRiskCity ? `${highestRiskCity.current_tipping_score.toFixed(1)} / 100 · ${highestBand?.label}` : 'No current score'}
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
                  {cityData.map((city, index) => {
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
                  const band = getRiskBand(city.current_tipping_score);
                  const cityName = formatCity(city.city_id);
                  const rank = city.rank ?? index + 1;

                  return (
                    <Link
                      key={city.city_id}
                      href={`/city/${city.city_id}`}
                      className={`city-risk-card risk-${band.tone}`}
                      aria-label={`View ${cityName.displayName} climate risk details`}
                    >
                      <div className="city-risk-card__header">
                        <span className="city-risk-card__rank">#{String(rank).padStart(2, '0')}</span>
                        <span className="city-risk-card__status">
                          <i className="risk-dot" aria-hidden="true" />
                          {band.label}
                        </span>
                      </div>

                      <div className="city-risk-card__title-row">
                        <h3>{cityName.cityName}</h3>
                        <span>{cityName.countryCode}</span>
                      </div>

                      <div className="city-risk-card__score-row">
                        <strong>{city.current_tipping_score.toFixed(1)}</strong>
                        <span>/ 100</span>
                      </div>

                      <div className="city-risk-card__meter" aria-hidden="true">
                        <span style={{ width: `${Math.min(100, Math.max(0, city.current_tipping_score))}%` }} />
                      </div>

                      <div className="city-risk-card__footer">
                        <span>Dominant driver</span>
                        <strong>{city.current_primary_driver || 'Unknown'}</strong>
                        <svg viewBox="0 0 16 16" fill="none" aria-hidden="true">
                          <path d="M3 8h9M8.5 4.5 12 8l-3.5 3.5" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" />
                        </svg>
                      </div>
                    </Link>
                  );
                })}
              </div>

              <footer className="dashboard-data-note">
                <span>Signal inputs</span>
                Heat · Wind · Rain · Air quality · River discharge
              </footer>
            </section>
          </>
        )}
      </div>
    </main>
  );
}
