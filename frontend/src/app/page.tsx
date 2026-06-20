import Link from 'next/link';
import { fetchCurrentScores } from '@/lib/api';

export default async function Dashboard() {
  const cityData = await fetchCurrentScores();

  // Calculate stats
  const activeRegions = cityData.length;
  const avgRisk = activeRegions > 0 
    ? cityData.reduce((acc, curr) => acc + curr.current_tipping_score, 0) / activeRegions 
    : 0;
  
  const highestRiskCity = activeRegions > 0 
    ? cityData.reduce((prev, current) => (prev.current_tipping_score > current.current_tipping_score) ? prev : current)
    : null;

  return (
    <main className="min-h-screen p-6 md:p-12 lg:p-20">
      <div className="max-w-7xl mx-auto space-y-12">
        
        {/* Hero Section */}
        <header className="flex flex-col items-center md:items-start text-center md:text-left space-y-6 mt-4">
          <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full bg-cyan-500/10 border border-cyan-500/20 text-xs font-semibold text-cyan-400 tracking-wide uppercase">
            <span className="w-2 h-2 rounded-full bg-cyan-400 animate-pulse"></span>
            Live Climate Intelligence
          </div>
          <h1 className="text-5xl md:text-7xl font-black tracking-tight text-slate-100">
            Global Tipping Risk
          </h1>
          <p className="text-lg md:text-xl text-slate-400 max-w-2xl font-medium">
            Real-time monitoring of critical climate thresholds and driver factors across major European metropolises.
          </p>
        </header>

        {cityData.length === 0 ? (
          <div className="glass-panel rounded-2xl p-12 text-center mt-12">
            <h2 className="text-2xl font-semibold mb-4 text-slate-200">System Initialization</h2>
            <p className="text-slate-400">Awaiting data stream from backend API...</p>
          </div>
        ) : (
          <>
            {/* Stats Summary Row */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
              <div className="glass-panel rounded-2xl p-6 flex flex-col justify-between">
                <span className="text-xs font-semibold uppercase tracking-widest text-slate-500 mb-4">Active Regions</span>
                <span className="text-4xl font-black text-slate-200">{activeRegions}</span>
              </div>
              <div className="glass-panel rounded-2xl p-6 flex flex-col justify-between">
                <span className="text-xs font-semibold uppercase tracking-widest text-slate-500 mb-4">Avg Global Risk</span>
                <span className={`text-4xl font-black ${avgRisk > 70 ? 'score-high' : avgRisk > 40 ? 'score-medium' : 'score-low'}`}>
                  {avgRisk.toFixed(1)}
                </span>
              </div>
              <div className="glass-panel rounded-2xl p-6 flex flex-col justify-between">
                <span className="text-xs font-semibold uppercase tracking-widest text-slate-500 mb-4">Highest Risk Region</span>
                <span className="text-3xl font-black text-slate-200 truncate">
                  {highestRiskCity ? highestRiskCity.city_id.replace('_', ', ').toUpperCase() : '--'}
                </span>
              </div>
            </div>

            {/* City Grid */}
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
              {cityData.map((city) => {
                let riskClass = 'score-low';
                let indicatorColor = 'bg-green-400';
                if (city.current_tipping_score > 70) {
                  riskClass = 'score-high';
                  indicatorColor = 'bg-red-400';
                } else if (city.current_tipping_score > 40) {
                  riskClass = 'score-medium';
                  indicatorColor = 'bg-amber-400';
                }

                return (
                  <Link
                    key={city.city_id}
                    href={`/city/${city.city_id}`}
                    className="glass-card rounded-2xl p-6 flex flex-col justify-between h-48 cursor-pointer city-card-link relative overflow-hidden group"
                  >
                    {/* Top glow line for severity */}
                    <div className={`absolute top-0 left-0 w-full h-1 ${indicatorColor} opacity-50 group-hover:opacity-100 transition-opacity`} />
                    
                    <div>
                      <h3 className="text-xl font-bold tracking-wide text-slate-100 mb-3">
                        {city.city_id.replace('_', ', ').toUpperCase()}
                      </h3>
                      <div className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-slate-800/40 border border-slate-700/50 text-[11px] font-semibold text-slate-300 uppercase tracking-wider">
                        Driver: <span className="text-cyan-400">{city.current_primary_driver || 'Unknown'}</span>
                      </div>
                    </div>

                    <div className="flex items-end justify-between">
                      <span className="text-[10px] font-bold text-slate-500 uppercase tracking-widest">
                        Tipping Score
                      </span>
                      <span className={`text-4xl font-black tracking-tight ${riskClass}`}>
                        {city.current_tipping_score.toFixed(1)}
                      </span>
                    </div>
                  </Link>
                );
              })}
            </div>
          </>
        )}
      </div>
    </main>
  );
}
