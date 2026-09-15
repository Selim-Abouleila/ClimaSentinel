import Link from "next/link";
import { notFound } from "next/navigation";
import { fetchCityScores, type CityDetail, type SignalStatus } from "@/lib/api";
import {
  getSnapshotFreshness,
  normalizeSignalReading,
} from "@/lib/signal-availability";

type RiskTone = "stable" | "monitoring" | "tipping" | "critical";

interface RiskBand {
  label: string;
  tone: RiskTone;
  range: string;
}

interface ScoreFactor {
  label: string;
  score: number | null;
  status: SignalStatus | "not_reported";
  monitored: boolean;
  available: boolean;
  coverage: number | null;
  band: RiskBand | null;
}

const RISK_BANDS: RiskBand[] = [
  { label: "Stable", tone: "stable", range: "0–30" },
  { label: "Monitoring", tone: "monitoring", range: "31–60" },
  { label: "Tipping", tone: "tipping", range: "61–80" },
  { label: "Critical", tone: "critical", range: "81–100" },
];

function getRiskBand(score: number): RiskBand {
  if (score >= 81) return RISK_BANDS[3];
  if (score >= 61) return RISK_BANDS[2];
  if (score >= 31) return RISK_BANDS[1];
  return RISK_BANDS[0];
}

function formatCity(cityId: string) {
  const [city = cityId, country = ""] = cityId.split("_");
  return {
    cityName: city.charAt(0).toUpperCase() + city.slice(1),
    countryCode: country.toUpperCase(),
  };
}

function normalizeDriver(value: string) {
  return value.toLowerCase().replace(/[^a-z]/g, "");
}

function normalizeFactor(
  label: string,
  score: number | null,
  status: SignalStatus | undefined,
  monitored: boolean | undefined,
  available: boolean | undefined,
  coverage: number | null | undefined,
): ScoreFactor {
  const normalized = normalizeSignalReading(
    score,
    status,
    monitored,
    available,
    coverage,
  );

  return {
    label,
    ...normalized,
    band: normalized.score === null ? null : getRiskBand(normalized.score),
  };
}

function buildFactors(city: CityDetail): ScoreFactor[] {
  return [
    normalizeFactor("Heat", city.heat_score, city.heat_status, city.heat_monitored, city.heat_available, city.heat_coverage),
    normalizeColdFactor(city),
    normalizeFactor("Wind", city.wind_score, city.wind_status, city.wind_monitored, city.wind_available, city.wind_coverage),
    normalizeFactor("Rain", city.rain_score, city.rain_status, city.rain_monitored, city.rain_available, city.rain_coverage),
    normalizeFactor("Air Quality", city.air_score, city.air_status, city.air_monitored, city.air_available, city.air_coverage),
    normalizeFactor("River / Flood", city.river_score, city.river_status, city.river_monitored, city.river_available, city.river_coverage),
  ];
}

function normalizeColdFactor(city: CityDetail): ScoreFactor {
  const notReported = [city.cold_score, city.cold_status, city.cold_monitored,
    city.cold_available, city.cold_coverage].every((value) => value === undefined);
  if (notReported) {
    return { label: "Cold", score: null, status: "not_reported", monitored: false,
      available: false, coverage: null, band: null };
  }

  // Cold has no legacy numeric-only contract. Require its availability metadata
  // before displaying a score, including zero; partial coverage stays unavailable.
  const status = city.cold_monitored === false ? "not_monitored"
    : city.cold_status === "available" && city.cold_monitored === true && city.cold_available === true
      ? "available" : city.cold_status === "not_monitored" ? "not_monitored" : "unavailable";
  return normalizeFactor("Cold", city.cold_score ?? null, status,
    city.cold_monitored, city.cold_available, city.cold_coverage);
}

function getAggregateCounts(city: CityDetail, factors: ScoreFactor[]) {
  const monitored = city.monitored_factor_count;
  const available = city.available_factor_count;
  if (typeof monitored === "number" && Number.isInteger(monitored) && monitored >= 0
    && typeof available === "number" && Number.isInteger(available) && available >= 0
    && available <= monitored) {
    return { monitored, available };
  }
  // A missing mode is unknown. Never infer inclusion from a count or Cold score.
  if (city.cold_in_global_score === undefined) return null;
  const participating = factors.filter((factor) => factor.label !== "Cold" || city.cold_in_global_score === true);
  return {
    monitored: participating.filter((factor) => factor.monitored).length,
    available: participating.filter((factor) => factor.available).length,
  };
}

function getFactorStatusLabel(factor: ScoreFactor) {
  if (factor.status === "not_reported") return "Not reported";
  if (factor.status === "not_monitored") return "Not monitored";
  if (factor.status === "unavailable") return "Unavailable";
  return factor.band?.label ?? "Unavailable";
}

function getCoverageLabel(factor: ScoreFactor) {
  if (factor.status === "not_reported") return "Cold data not reported";
  if (factor.status === "not_monitored") return "No source configured";
  if (factor.coverage === null) {
    return factor.status === "available" ? "Coverage not reported" : "Coverage unavailable";
  }
  return `${Math.round(factor.coverage * 100)}% ${factor.label === "Cold" ? "daily temperature" : "window"} coverage`;
}

export default async function CityDetailPage({
  params,
}: {
  params: Promise<{ city_id: string }>;
}) {
  const { city_id } = await params;
  const city = await fetchCityScores(city_id);

  if (!city) notFound();

  const cityName = formatCity(city_id);
  const hasGlobalScore = typeof city.current_tipping_score === "number"
    && Number.isFinite(city.current_tipping_score) && city.current_score_available !== false;
  const globalScore = hasGlobalScore ? city.current_tipping_score : null;
  const globalBand = globalScore === null ? null : getRiskBand(globalScore);
  const factors = buildFactors(city);
  const reportedDriver = city.current_primary_driver || "Unknown";
  const driverLabel = normalizeDriver(reportedDriver) === "cold" && city.cold_in_global_score !== true
    ? "Unknown" : reportedDriver;
  const primaryDriver = normalizeDriver(driverLabel);
  const aggregateCounts = getAggregateCounts(city, factors);
  const aggregateCoverage = typeof city.overall_coverage === "number" && Number.isFinite(city.overall_coverage)
    && city.overall_coverage >= 0 && city.overall_coverage <= 1
    ? `${Math.round(city.overall_coverage * 100)}% aggregate coverage.` : null;
  const coldContribution = city.cold_in_global_score === true
    ? "Cold is included in the current tipping score when available."
    : city.cold_in_global_score === false
      ? "Cold is shown separately from the current tipping score."
      : "Cold’s contribution to the current tipping score is not reported.";
  const snapshot = getSnapshotFreshness(city.operational_ingested_at_utc);
  const snapshotLabel = snapshot?.ingestedAt.toLocaleString("en-GB", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
    timeZone: "UTC",
  });

  return (
    <main className="subpage-shell city-detail-page">
      <div className="subpage-container subpage-container--detail">
        <Link href="/" className="subpage-back-link">
          <svg viewBox="0 0 16 16" fill="none" aria-hidden="true">
            <path d="M13 8H3m4-4L3 8l4 4" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
          Back to overview
        </Link>

        <header className={`city-detail-hero ${globalBand ? `risk-${globalBand.tone}` : "signal-unavailable"}`}>
          <div className="city-detail-hero__identity">
            <div className="dashboard-eyebrow">
              <span className="dashboard-eyebrow__dot" aria-hidden="true" />
              City profile · Today / tomorrow (UTC)
            </div>
            <div className="city-detail-hero__title">
              <h1>{cityName.cityName}</h1>
              <span>{cityName.countryCode}</span>
            </div>
            <p>
              {globalScore !== null
                ? "Current climate stress composition from available monitored signals."
                : "The current tipping score is unavailable. Individual signal readings are shown below."}
            </p>
            <div className="city-detail-hero__metadata">
              <span>
                <small>Dominant driver</small>
                <strong>{globalScore === null ? "Unavailable" : driverLabel}</strong>
              </span>
              <span className="city-detail-hero__band">
                <small>Risk band</small>
                <strong>
                  <i className="risk-dot" aria-hidden="true" />
                  {globalBand?.label ?? "Unavailable"}
                </strong>
              </span>
            </div>
          </div>

          <div className="city-detail-hero__score">
            <span>Current tipping score</span>
            <div>
              <strong>{globalScore === null ? "—" : globalScore.toFixed(1)}</strong>
              {globalScore !== null && <small>/ 100</small>}
            </div>
            <div
              className="city-detail-hero__meter"
              role="img"
              aria-label={globalScore === null
                ? "Current tipping score unavailable"
                : `Current tipping score: ${globalScore.toFixed(1)} out of 100`}
            >
              {globalScore !== null && (
                <span style={{ width: `${Math.min(100, Math.max(0, globalScore))}%` }} />
              )}
            </div>
            <p>{globalBand ? `${globalBand.range} · ${globalBand.label}` : "Unavailable · No aggregate score"}</p>
          </div>
        </header>

        <section className="city-factor-panel" aria-labelledby="factor-breakdown-title">
          <header className="city-factor-panel__header">
            <div>
              <span className="section-kicker">Factor Breakdown</span>
              <h2 id="factor-breakdown-title">Current signal composition</h2>
              <p>Each factor is scored independently on the same zero-to-one-hundred scale.</p>
              <div className="city-factor-panel__composition" role="region" aria-label="Overall score composition">
                <p className="city-factor-panel__availability">
                  {aggregateCounts
                    ? `${aggregateCounts.available} of ${aggregateCounts.monitored} monitored signals available for the current score.`
                    : "Aggregate availability not reported."}
                  {aggregateCoverage && ` ${aggregateCoverage}`}
                  {" "}Missing signals are excluded from the overall score.
                </p>
                <p className="city-factor-panel__availability">{coldContribution}</p>
              </div>
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
          </header>

          <div className="city-factor-list">
            {factors.map((factor, index) => {
              const isPrimary = globalScore !== null && factor.available
                && normalizeDriver(factor.label) === primaryDriver;
              const score = factor.score === null ? null : Math.min(100, Math.max(0, factor.score));
              const statusLabel = getFactorStatusLabel(factor);
              const stateClass = factor.status === "available" && factor.band
                ? `risk-${factor.band.tone}`
                : `signal-${factor.status.replace("_", "-")}`;

              return (
                <article
                  key={factor.label}
                  className={`city-factor-row ${stateClass}`}
                  aria-label={`${factor.label} signal: ${statusLabel}`}
                >
                  <span className="city-factor-row__index">{String(index + 1).padStart(2, "0")}</span>
                  <div className="city-factor-row__identity">
                    <h3>{factor.label}</h3>
                    {isPrimary && <span>Dominant driver</span>}
                  </div>
                  <div className="city-factor-row__status">
                    <span className="city-factor-row__status-label">
                      <i className="risk-dot" aria-hidden="true" />
                      {statusLabel}
                    </span>
                    <small>{getCoverageLabel(factor)}</small>
                  </div>
                  <div className="city-factor-row__score">
                    <strong>{factor.score === null ? "—" : factor.score.toFixed(1)}</strong>
                    {factor.score !== null && <span>/ 100</span>}
                  </div>
                  <div
                    className="city-factor-row__meter"
                    role="img"
                    aria-label={score === null
                      ? `${factor.label}: ${statusLabel.toLowerCase()}`
                      : `${factor.label}: ${factor.score?.toFixed(1)} out of 100`}
                  >
                    {score !== null && <span style={{ width: `${score}%` }} />}
                  </div>
                </article>
              );
            })}
          </div>
        </section>

        {snapshot && (
          <div
            className={`dashboard-freshness dashboard-freshness--content-footer ${snapshot.stale ? "is-stale" : ""}`}
            role="status"
            aria-label={snapshot.stale ? "Data snapshot is stale" : "Selected data snapshot"}
          >
            <span>{snapshot.stale ? "Stale data snapshot" : "Selected data snapshot"}</span>
            <time dateTime={snapshot.ingestedAt.toISOString()}>{snapshotLabel} UTC</time>
            <small>
              {snapshot.stale
                ? "The scheduled daily ingestion is overdue; interpret scores cautiously."
                : "One exact ingestion run is used across all available signals."}
            </small>
          </div>
        )}

        <footer className="dashboard-data-note">
          <span>Signal catalogue</span>
          Heat · Cold · Wind · Rain · Air quality · River discharge · Availability varies by city
        </footer>
      </div>
    </main>
  );
}
