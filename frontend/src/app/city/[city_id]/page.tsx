import Link from "next/link";
import { notFound } from "next/navigation";
import { fetchCityScores, CityDetail } from "@/lib/api";

type RiskTone = "stable" | "monitoring" | "tipping" | "critical";

interface RiskBand {
  label: string;
  tone: RiskTone;
  range: string;
}

interface ScoreFactor {
  label: string;
  score: number;
  band: RiskBand;
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

function buildFactors(city: CityDetail): ScoreFactor[] {
  return [
    { label: "Heat", score: city.heat_score, band: getRiskBand(city.heat_score) },
    { label: "Wind", score: city.wind_score, band: getRiskBand(city.wind_score) },
    { label: "Rain", score: city.rain_score, band: getRiskBand(city.rain_score) },
    { label: "Air Quality", score: city.air_score, band: getRiskBand(city.air_score) },
    { label: "River / Flood", score: city.river_score, band: getRiskBand(city.river_score) },
  ];
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
  const globalBand = getRiskBand(city.current_tipping_score);
  const factors = buildFactors(city);
  const primaryDriver = normalizeDriver(city.current_primary_driver);

  return (
    <main className="subpage-shell city-detail-page">
      <div className="subpage-container subpage-container--detail">
        <Link href="/" className="subpage-back-link">
          <svg viewBox="0 0 16 16" fill="none" aria-hidden="true">
            <path d="M13 8H3m4-4L3 8l4 4" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
          Back to overview
        </Link>

        <header className={`city-detail-hero risk-${globalBand.tone}`}>
          <div className="city-detail-hero__identity">
            <div className="dashboard-eyebrow">
              <span className="dashboard-eyebrow__dot" aria-hidden="true" />
              City profile · Current 48-hour window
            </div>
            <div className="city-detail-hero__title">
              <h1>{cityName.cityName}</h1>
              <span>{cityName.countryCode}</span>
            </div>
            <p>Current climate stress composition across five monitored signals.</p>
            <div className="city-detail-hero__metadata">
              <span>
                <small>Dominant driver</small>
                <strong>{city.current_primary_driver}</strong>
              </span>
              <span className="city-detail-hero__band">
                <i className="risk-dot" aria-hidden="true" />
                <small>Risk band</small>
                <strong>{globalBand.label}</strong>
              </span>
            </div>
          </div>

          <div className="city-detail-hero__score">
            <span>Current tipping score</span>
            <div>
              <strong>{city.current_tipping_score.toFixed(1)}</strong>
              <small>/ 100</small>
            </div>
            <div className="city-detail-hero__meter" aria-hidden="true">
              <span style={{ width: `${Math.min(100, Math.max(0, city.current_tipping_score))}%` }} />
            </div>
            <p>{globalBand.range} · {globalBand.label}</p>
          </div>
        </header>

        <section className="city-factor-panel" aria-labelledby="factor-breakdown-title">
          <header className="city-factor-panel__header">
            <div>
              <span className="section-kicker">Factor Breakdown</span>
              <h2 id="factor-breakdown-title">Current signal composition</h2>
              <p>Each factor is scored independently on the same zero-to-one-hundred scale.</p>
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
              const isPrimary = normalizeDriver(factor.label) === primaryDriver;
              const score = Math.min(100, Math.max(0, factor.score));

              return (
                <article key={factor.label} className={`city-factor-row risk-${factor.band.tone}`}>
                  <span className="city-factor-row__index">{String(index + 1).padStart(2, "0")}</span>
                  <div className="city-factor-row__identity">
                    <h3>{factor.label}</h3>
                    {isPrimary && <span>Dominant driver</span>}
                  </div>
                  <div className="city-factor-row__status">
                    <i className="risk-dot" aria-hidden="true" />
                    {factor.band.label}
                  </div>
                  <div className="city-factor-row__score">
                    <strong>{factor.score.toFixed(1)}</strong>
                    <span>/ 100</span>
                  </div>
                  <div className="city-factor-row__meter" aria-label={`${factor.label}: ${factor.score.toFixed(1)} out of 100`}>
                    <span style={{ width: `${score}%` }} />
                  </div>
                </article>
              );
            })}
          </div>
        </section>

        <footer className="dashboard-data-note">
          <span>Signal inputs</span>
          Heat · Wind · Rain · Air quality · River discharge
        </footer>
      </div>
    </main>
  );
}
