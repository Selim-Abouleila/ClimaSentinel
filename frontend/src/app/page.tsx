import { fetchCurrentScores, fetchCurrentZones } from '@/lib/api';

export default async function Dashboard() {
  const [scores, zones] = await Promise.all([
    fetchCurrentScores(),
    fetchCurrentZones()
  ]);

  // Merge the two arrays based on city_id for a clean display
  const cityData = scores.map(score => {
    const zoneInfo = zones.find(z => z.city_id === score.city_id);
    return {
      ...score,
      current_zone: zoneInfo?.current_zone || 'Unknown'
    };
  });

  return (
    <main className="min-h-screen p-8 md:p-16 lg:p-24">
      <div className="max-w-6xl mx-auto">
        <header className="mb-12 text-center md:text-left">
          <h1 className="text-4xl md:text-6xl font-bold mb-4 bg-clip-text text-transparent bg-gradient-to-r from-sky-400 to-pink-400">
            ClimaSentinel
          </h1>
          <p className="text-xl text-slate-300">
            Live Global Climate Tipping Risk Dashboard
          </p>
        </header>

        {cityData.length === 0 ? (
          <div className="glass-panel rounded-2xl p-12 text-center">
            <h2 className="text-2xl font-semibold mb-4 text-slate-200">Waiting for data...</h2>
            <p className="text-slate-400">Ensure your FastAPI backend is running and connected.</p>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {cityData.map((city) => {
              // Determine text color based on risk score
              let riskClass = 'score-low';
              if (city.current_tipping_score > 70) riskClass = 'score-high';
              else if (city.current_tipping_score > 40) riskClass = 'score-medium';

              return (
                <div key={city.city_id} className="glass-card rounded-2xl p-6 flex flex-col justify-between h-48">
                  <div>
                    <h3 className="text-xl font-bold uppercase tracking-wider text-slate-100 mb-1">
                      {city.city_id.replace('_', ', ')}
                    </h3>
                    <div className="inline-block px-3 py-1 rounded-full bg-slate-800/50 border border-slate-700/50 text-xs font-medium text-slate-300 mb-4">
                      Zone: {city.current_zone}
                    </div>
                  </div>
                  
                  <div className="flex items-end justify-between">
                    <span className="text-sm font-medium text-slate-400 uppercase tracking-widest">
                      Risk Score
                    </span>
                    <span className={`text-4xl font-black ${riskClass}`}>
                      {city.current_tipping_score.toFixed(1)}
                    </span>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </main>
  );
}
