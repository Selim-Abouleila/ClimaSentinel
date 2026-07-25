"use client";

import { useState } from "react";
import type { CityForecast } from "@/lib/api";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";

type RiskTone = "stable" | "monitoring" | "tipping" | "critical";

interface RiskBand {
  label: string;
  tone: RiskTone;
}

const ALL_CITIES = [
  { id: "stockholm_se", name: "Stockholm, SE" },
  { id: "warsaw_pl", name: "Warsaw, PL" },
  { id: "berlin_de", name: "Berlin, DE" },
  { id: "paris_fr", name: "Paris, FR" },
  { id: "london_gb", name: "London, GB" },
  { id: "rome_it", name: "Rome, IT" },
  { id: "madrid_es", name: "Madrid, ES" },
  { id: "lisbon_pt", name: "Lisbon, PT" },
  { id: "athens_gr", name: "Athens, GR" },
  { id: "amsterdam_nl", name: "Amsterdam, NL" },
];

const HORIZON_OPTIONS = [
  { days: 1, label: "+1 Day", subtitle: "Tomorrow" },
  { days: 2, label: "+2 Days", subtitle: "48 hours" },
  { days: 3, label: "+3 Days", subtitle: "72 hours" },
];

const FORECAST_FACTORS = [
  { title: "Heat Score Forecast", label: "Heat", key: "heat_score" },
  { title: "Wind Score Forecast", label: "Wind", key: "wind_score" },
  { title: "Rain Score Forecast", label: "Rain", key: "rain_score" },
  { title: "Air Quality Forecast", label: "Air quality", key: "air_score" },
  { title: "River Flood Forecast", label: "River / flood", key: "river_score" },
] as const;

function getRiskBand(score: number): RiskBand {
  if (score >= 81) return { label: "Critical", tone: "critical" };
  if (score >= 61) return { label: "Tipping", tone: "tipping" };
  if (score >= 31) return { label: "Monitoring", tone: "monitoring" };
  return { label: "Stable", tone: "stable" };
}

function clampScore(score: number) {
  return Math.min(100, Math.max(0, score));
}

export default function ForecastPage() {
  const [selectedCity, setSelectedCity] = useState<string | null>(null);
  const [forecast, setForecast] = useState<CityForecast | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(false);
  const [horizonDays, setHorizonDays] = useState(3);

  const fetchForecast = async (cityId: string, horizon: number) => {
    setForecast(null);
    setError(false);
    setLoading(true);

    try {
      const res = await fetch(
        `${API_BASE_URL}/data/city/${encodeURIComponent(cityId)}/forecast?horizon_days=${horizon}`,
        { cache: "no-store" }
      );
      if (!res.ok) throw new Error("Failed to fetch forecast");
      const data: CityForecast = await res.json();
      setForecast(data);
    } catch {
      setError(true);
    } finally {
      setLoading(false);
    }
  };

  const handleCityClick = (cityId: string) => {
    setSelectedCity(cityId);
    fetchForecast(cityId, horizonDays);
  };

  const handleHorizonChange = (days: number) => {
    setHorizonDays(days);
    if (selectedCity) fetchForecast(selectedCity, days);
  };

  const currentCity = ALL_CITIES.find((city) => city.id === selectedCity);
  const forecastBand = forecast
    ? getRiskBand(forecast.estimated_total_tipping_score)
    : null;
  const baselineBand = forecast ? getRiskBand(forecast.current_tipping_score) : null;
  const delta = forecast
    ? forecast.estimated_total_tipping_score - forecast.current_tipping_score
    : 0;
  const targetPrecipitation = forecast
    ? forecast.weather_trajectory[`precip_plus_${horizonDays}d`]
    : null;
  const targetWind = forecast
    ? forecast.weather_trajectory[`wind_plus_${horizonDays}d`]
    : null;
  return (
    <main className="subpage-shell forecast-page">
      <div className="subpage-container">
        <header className="subpage-hero">
          <div className="dashboard-eyebrow">
            <span className="dashboard-eyebrow__dot" aria-hidden="true" />
            Rule-based outlook · 1–3 days
          </div>
          <div className="subpage-hero__title-row">
            <h1>Climate Risk Forecast</h1>
            <span
              className="model-status model-status--beta"
              aria-label="Forecast feature is in beta"
            >
              Beta forecast
            </span>
          </div>
          <p>
            Experimental, rule-based climate risk projections by city for the
            next 1–3 days.
          </p>
        </header>

        <section className="forecast-controls" aria-label="Forecast controls">
          <div className="forecast-control-group">
            <div className="forecast-control-group__header">
              <div>
                <span className="section-kicker">Location</span>
                <h2>Select a city</h2>
              </div>
              <span>{selectedCity ? currentCity?.name : "No city selected"}</span>
            </div>
            <div className="forecast-city-grid">
              {ALL_CITIES.map((city) => {
                const isSelected = city.id === selectedCity;
                return (
                  <button
                    key={city.id}
                    type="button"
                    onClick={() => handleCityClick(city.id)}
                    disabled={loading}
                    aria-pressed={isSelected}
                    className={isSelected ? "is-selected" : ""}
                  >
                    {city.name}
                  </button>
                );
              })}
            </div>
          </div>

          <div className="forecast-control-divider" aria-hidden="true" />

          <div className="forecast-control-group forecast-control-group--horizon">
            <div className="forecast-control-group__header">
              <div>
                <span className="section-kicker">Horizon</span>
                <h2>Projection window</h2>
              </div>
              <span>Target: Day +{horizonDays}</span>
            </div>
            <div className="forecast-horizon-grid">
              {HORIZON_OPTIONS.map((option) => {
                const isActive = option.days === horizonDays;
                return (
                  <button
                    key={option.days}
                    type="button"
                    onClick={() => handleHorizonChange(option.days)}
                    disabled={loading}
                    aria-pressed={isActive}
                    className={isActive ? "is-selected" : ""}
                  >
                    <strong>{option.label}</strong>
                    <span>{option.subtitle}</span>
                  </button>
                );
              })}
            </div>
          </div>
        </section>

        <aside
          className="forecast-validation-note"
          aria-label="Forecast note"
        >
          <strong>About the scores</strong>
          <p>
            Heat has limited backtest evidence; Rain performed poorly in
            backtests; Wind, air quality and river lack observed validation.
            Scores are point estimates without confidence bands. Missing inputs
            are marked unavailable.
          </p>
        </aside>

        {!selectedCity && (
          <section className="forecast-state" aria-labelledby="forecast-empty-title">
            <span className="forecast-state__symbol" aria-hidden="true">
              <i />
            </span>
            <span className="section-kicker">Awaiting input</span>
            <h2 id="forecast-empty-title">Select a city</h2>
            <p>Choose a city to view its Day +{horizonDays} forecast.</p>
          </section>
        )}

        {loading && selectedCity && (
          <section className="forecast-state" role="status" aria-live="polite">
            <span className="forecast-loader" aria-hidden="true" />
            <span className="section-kicker">Forecast</span>
            <h2>Calculating Forecast</h2>
            <p>Calculating {currentCity?.name} at Day +{horizonDays}.</p>
          </section>
        )}

        {error && !loading && selectedCity && (
          <section className="forecast-state forecast-state--error" role="alert">
            <span className="forecast-state__symbol" aria-hidden="true">!</span>
            <span className="section-kicker">Connection error</span>
            <h2>Forecast Unavailable</h2>
            <p>
              The forecast output for {currentCity?.name} could not be retrieved.
              Check the backend connection and try again.
            </p>
            <button type="button" onClick={() => fetchForecast(selectedCity, horizonDays)}>
              Retry forecast
            </button>
          </section>
        )}

        {forecast && !loading && forecastBand && baselineBand && (
          <div className="forecast-results" aria-live="polite">
            <header className="forecast-results__header">
              <div>
                <span className="section-kicker">Forecast output</span>
                <h2>{currentCity?.name} · Day +{horizonDays}</h2>
                <p>Forecast vintage date {forecast.prediction_date}</p>
              </div>
              <div className={`forecast-results__status risk-${forecastBand.tone}`}>
                <i className="risk-dot" aria-hidden="true" />
                {forecastBand.label} risk
              </div>
            </header>

            <section className="forecast-summary-grid" aria-label="Forecast summary">
              <article className={`forecast-summary-card risk-${forecastBand.tone}`}>
                <div className="forecast-summary-card__topline">
                  <span>Est. Total Risk (Day +{horizonDays})</span>
                  <small>01</small>
                </div>
                <div className="forecast-summary-card__metric">
                  <strong>{forecast.estimated_total_tipping_score.toFixed(1)}</strong>
                  <span>/ 100</span>
                </div>
                <p>Rule-based estimate</p>
              </article>

              <article className={`forecast-summary-card risk-${baselineBand.tone}`}>
                <div className="forecast-summary-card__topline">
                  <span>Current baseline</span>
                  <small>02</small>
                </div>
                <div className="forecast-summary-card__metric">
                  <strong>{forecast.current_tipping_score.toFixed(1)}</strong>
                  <span>/ 100</span>
                </div>
                <p className={delta > 0 ? "delta-increase" : delta < 0 ? "delta-decrease" : ""}>
                  {delta > 0 ? "+" : ""}{delta.toFixed(1)} projected change
                </p>
              </article>

              <article className="forecast-summary-card">
                <div className="forecast-summary-card__topline">
                  <span>Forecast driver</span>
                  <small>03</small>
                </div>
                <h3>{forecast.forecast_primary_driver}</h3>
                <p>Highest projected factor</p>
              </article>

              <article className="forecast-summary-card forecast-summary-card--weather">
                <div className="forecast-summary-card__topline">
                  <span>Weather trajectory</span>
                  <small>04</small>
                </div>
                <div className="forecast-weather-list">
                  {Array.from({ length: horizonDays }, (_, index) => index + 1).map((day) => {
                    const temperature = forecast.weather_trajectory[`temp_max_plus_${day}d`];
                    return (
                      <span key={day}>
                        <small>D+{day} max</small>
                        <strong>{temperature != null ? temperature.toFixed(1) : "—"}°</strong>
                      </span>
                    );
                  })}
                  <span>
                    <small>Rain D+{horizonDays}</small>
                    <strong>{targetPrecipitation != null ? targetPrecipitation.toFixed(1) : "—"} mm</strong>
                  </span>
                  <span>
                    <small>Wind D+{horizonDays}</small>
                    <strong>{targetWind != null ? targetWind.toFixed(1) : "—"} km/h</strong>
                  </span>
                </div>
              </article>
            </section>

            <section className="forecast-factors" aria-labelledby="forecast-factors-title">
              <div className="forecast-factors__header">
                <div>
                  <span className="section-kicker">Forecast components</span>
                  <h2 id="forecast-factors-title">Factor-level outlook</h2>
                  <p>Projected score by climate factor.</p>
                </div>
              </div>

              <div className="forecast-factor-grid">
                {FORECAST_FACTORS.map((factor, index) => {
                  const factorData = forecast.sub_scores_forecast[factor.key];
                  const estimatedScore = factorData.available
                    ? factorData.estimated_score
                    : null;
                  const factorBand = estimatedScore === null
                    ? null
                    : getRiskBand(estimatedScore);
                  const score = estimatedScore === null
                    ? null
                    : clampScore(estimatedScore);

                  return (
                    <article
                      key={factor.key}
                      aria-label={`${factor.label} forecast`}
                      className={`forecast-factor-card ${factorBand ? `risk-${factorBand.tone}` : "is-unavailable"}`}
                      data-forecast-method={factorData.method}
                    >
                      <div className="forecast-factor-card__topline">
                        <span>#{String(index + 1).padStart(2, "0")}</span>
                        <strong>
                          <i className="risk-dot" aria-hidden="true" />
                          {factorBand?.label ?? "Unavailable"}
                        </strong>
                      </div>
                      <h3>{factor.title}</h3>
                      <div className={`forecast-factor-card__score ${score === null ? "is-unavailable" : ""}`}>
                        <strong>{estimatedScore === null ? "—" : estimatedScore.toFixed(1)}</strong>
                        {estimatedScore !== null && <span>/ 100</span>}
                      </div>
                      <div
                        className={`forecast-factor-card__meter ${score === null ? "is-unavailable" : ""}`}
                        aria-hidden="true"
                      >
                        {score !== null && (
                          <>
                            <span className="forecast-factor-card__fill" style={{ width: `${score}%` }} />
                            <i style={{ left: `${score}%` }} />
                          </>
                        )}
                      </div>
                      {score === null && (
                        <p
                          className="forecast-factor-card__context"
                          title={factorData.unavailable_reason ?? undefined}
                        >
                          Source data unavailable
                        </p>
                      )}
                    </article>
                  );
                })}
              </div>
            </section>

          </div>
        )}
      </div>
    </main>
  );
}
