import Link from 'next/link';
import { fetchCityScores, CityDetail } from '@/lib/api';
import { notFound } from 'next/navigation';

// ── Types ─────────────────────────────────────────────────────────────────

interface ScoreFactor {
  label: string;
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
    { label: 'Heat',          score: city.heat_score,  colorClass: getScoreColorClass(city.heat_score),  barColor: getBarColor(city.heat_score)  },
    { label: 'Wind',          score: city.wind_score,  colorClass: getScoreColorClass(city.wind_score),  barColor: getBarColor(city.wind_score)  },
    { label: 'Rain',          score: city.rain_score,  colorClass: getScoreColorClass(city.rain_score),  barColor: getBarColor(city.rain_score)  },
    { label: 'Air Quality',   score: city.air_score,   colorClass: getScoreColorClass(city.air_score),   barColor: getBarColor(city.air_score)   },
    { label: 'River / Flood', score: city.river_score, colorClass: getScoreColorClass(city.river_score), barColor: getBarColor(city.river_score) },
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
    <main className="min-h-screen p-6 md:p-12 lg:p-20">
      <div className="max-w-4xl mx-auto">

        {/* ── Back link ──────────────────────────────────────────────── */}
        <Link
          href="/"
          className="inline-flex items-center gap-2 text-sm font-medium text-slate-400 hover:text-slate-100 transition-colors mb-10 group"
        >
          <svg className="w-4 h-4 transition-transform group-hover:-translate-x-1" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M10 19l-7-7m0 0l7-7m-7 7h18" />
          </svg>
          Back to Dashboard
        </Link>

        {/* ── City header ────────────────────────────────────────────── */}
        <header className="glass-panel rounded-2xl p-8 md:p-10 mb-8 border-t border-t-white/10 relative overflow-hidden">
          <div className="absolute top-0 right-0 w-64 h-64 bg-cyan-500/5 rounded-full blur-3xl -translate-y-1/2 translate-x-1/3"></div>
          <div className="flex flex-col md:flex-row md:items-end justify-between gap-8 relative z-10">
            <div>
              <p className="text-xs font-bold uppercase tracking-widest text-slate-500 mb-2">
                Region Analytics
              </p>
              <h1 className="text-4xl md:text-5xl font-black tracking-tight text-slate-100 mb-4">
                {formatCity(city_id)}
              </h1>
              <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-lg bg-slate-800/60 border border-slate-700/50 text-xs font-bold text-slate-300 uppercase tracking-widest shadow-inner">
                Primary Driver: <span className="text-cyan-400">{city.current_primary_driver}</span>
              </div>
            </div>

            <div className="text-left md:text-right">
              <p className="text-xs font-bold text-slate-500 uppercase tracking-widest mb-2">
                Global Tipping Score
              </p>
              <span className={`text-6xl md:text-7xl font-black tracking-tighter ${globalColorClass}`}>
                {city.current_tipping_score.toFixed(1)}
              </span>
            </div>
          </div>
        </header>

        {/* ── Sub-score breakdown ────────────────────────────────────── */}
        <section className="glass-panel rounded-2xl p-8 md:p-10">
          <h2 className="text-xs font-bold uppercase tracking-widest text-slate-500 mb-8">
            Factor Breakdown
          </h2>

          <div className="flex flex-col gap-8">
            {factors.map((f) => (
              <div key={f.label} className="group">
                {/* Label row */}
                <div className="flex items-center justify-between mb-3">
                  <span className="text-sm font-semibold tracking-wide text-slate-400 group-hover:text-slate-100 transition-colors">
                    {f.label}
                  </span>
                  <span className={`text-xl font-black tabular-nums tracking-tight ${f.colorClass}`}>
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
                      boxShadow: `0 0 12px ${f.barColor}80`,
                    }}
                  />
                </div>
              </div>
            ))}
          </div>

          {/* ── Score legend ────────────────────────────────────────────── */}
          <div className="flex items-center justify-between md:justify-start gap-8 mt-12 pt-8 border-t border-white/5 text-[10px] font-bold text-slate-500 uppercase tracking-widest">
            <span className="flex items-center gap-2"><span className="w-2 h-2 rounded-full bg-green-400 shadow-[0_0_8px_rgba(74,222,128,0.5)]" /> Low &lt; 40</span>
            <span className="flex items-center gap-2"><span className="w-2 h-2 rounded-full bg-amber-400 shadow-[0_0_8px_rgba(251,191,36,0.5)]" /> Med 40–70</span>
            <span className="flex items-center gap-2"><span className="w-2 h-2 rounded-full bg-red-400 shadow-[0_0_8px_rgba(248,113,113,0.5)]" /> High &gt; 70</span>
          </div>
        </section>
      </div>
    </main>
  );
}
