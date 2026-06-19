import Link from 'next/link';
import { fetchCityScores, CityDetail } from '@/lib/api';
import { notFound } from 'next/navigation';

// ── Types ─────────────────────────────────────────────────────────────────

interface ScoreFactor {
  label: string;
  emoji: string;
  score: number;
  colorClass: string;
  barColor: string;
}

// ── Helpers ───────────────────────────────────────────────────────────────

function getScoreColorClass(score: number): string {
  if (score > 70) return 'score-high';
  if (score > 40) return 'score-medium';
  return 'score-low';
}

function getBarColor(score: number): string {
  if (score > 70) return '#f87171';  // red
  if (score > 40) return '#fbbf24';  // amber
  return '#4ade80';                   // green
}

function formatCity(city_id: string): string {
  return city_id.replace('_', ', ').toUpperCase();
}

function buildFactors(city: CityDetail): ScoreFactor[] {
  return [
    { label: 'Heat',          emoji: '🌡️', score: city.heat_score,  colorClass: getScoreColorClass(city.heat_score),  barColor: getBarColor(city.heat_score)  },
    { label: 'Wind',          emoji: '💨', score: city.wind_score,  colorClass: getScoreColorClass(city.wind_score),  barColor: getBarColor(city.wind_score)  },
    { label: 'Rain',          emoji: '🌧️', score: city.rain_score,  colorClass: getScoreColorClass(city.rain_score),  barColor: getBarColor(city.rain_score)  },
    { label: 'Air Quality',   emoji: '🌫️', score: city.air_score,   colorClass: getScoreColorClass(city.air_score),   barColor: getBarColor(city.air_score)   },
    { label: 'River / Flood', emoji: '🌊', score: city.river_score, colorClass: getScoreColorClass(city.river_score), barColor: getBarColor(city.river_score) },
  ];
}

// ── Page ──────────────────────────────────────────────────────────────────

export default async function CityDetailPage({
  params,
}: {
  params: Promise<{ city_id: string }>;
}) {
  const { city_id } = await params;
  const city = await fetchCityScores(city_id);

  if (!city) notFound();

  const factors = buildFactors(city);
  const globalColorClass = getScoreColorClass(city.current_tipping_score);

  return (
    <main className="min-h-screen p-8 md:p-16 lg:p-24">
      <div className="max-w-2xl mx-auto">

        {/* ── Back link ──────────────────────────────────────────────── */}
        <Link
          href="/"
          className="inline-flex items-center gap-2 text-sm text-sky-400 hover:text-sky-300 transition-colors mb-10 group"
        >
          <span className="group-hover:-translate-x-1 transition-transform">←</span>
          Back to Dashboard
        </Link>

        {/* ── City header ────────────────────────────────────────────── */}
        <header className="glass-panel rounded-2xl p-8 mb-6">
          <p className="text-xs font-semibold uppercase tracking-widest text-slate-400 mb-1">
            City Detail
          </p>
          <h1 className="text-4xl font-black uppercase tracking-wider text-slate-100 mb-3">
            {formatCity(city_id)}
          </h1>

          <div className="flex items-center justify-between flex-wrap gap-4 mt-4">
            <div>
              <p className="text-xs font-medium text-slate-400 uppercase tracking-widest mb-1">
                Global Tipping Score
              </p>
              <span className={`text-5xl font-black ${globalColorClass}`}>
                {city.current_tipping_score.toFixed(1)}
              </span>
            </div>
            <div
              className="inline-flex items-center gap-2 px-4 py-2 rounded-full border text-sm font-semibold"
              style={{ borderColor: 'rgba(56,189,248,0.4)', color: '#38bdf8', background: 'rgba(56,189,248,0.08)' }}
            >
              Primary driver: {city.current_primary_driver}
            </div>
          </div>
        </header>

        {/* ── Sub-score breakdown ────────────────────────────────────── */}
        <section className="glass-panel rounded-2xl p-8">
          <h2 className="text-sm font-semibold uppercase tracking-widest text-slate-400 mb-6">
            Factor Breakdown
          </h2>

          <div className="flex flex-col gap-7">
            {factors.map((f) => (
              <div key={f.label}>

                {/* Label row */}
                <div className="flex items-center justify-between mb-2">
                  <div className="flex items-center gap-2">
                    <span className="text-lg leading-none">{f.emoji}</span>
                    <span className="text-sm font-semibold text-slate-200">{f.label}</span>
                  </div>
                  <span className={`text-xl font-black tabular-nums ${f.colorClass}`}>
                    {f.score.toFixed(1)}
                  </span>
                </div>

                {/* Progress bar */}
                <div className="score-bar-track">
                  <div
                    className="score-bar-fill"
                    style={{
                      width: `${f.score}%`,
                      background: f.barColor,
                      boxShadow: `0 0 10px ${f.barColor}60`,
                    }}
                  />
                </div>

              </div>
            ))}
          </div>
        </section>

        {/* ── Score legend ────────────────────────────────────────────── */}
        <div className="flex items-center gap-6 mt-6 justify-center text-xs text-slate-500">
          <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-green-400 inline-block" /> Low (&lt; 40)</span>
          <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-amber-400 inline-block" /> Medium (40–70)</span>
          <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-red-400 inline-block" /> High (&gt; 70)</span>
        </div>

      </div>
    </main>
  );
}
