import Link from 'next/link';
import { fetchCityForecast } from '@/lib/api';

const ALL_CITIES = [
  { id: 'stockholm_se', name: 'Stockholm, SE' },
  { id: 'warsaw_pl', name: 'Warsaw, PL' },
  { id: 'berlin_de', name: 'Berlin, DE' },
  { id: 'paris_fr', name: 'Paris, FR' },
  { id: 'london_gb', name: 'London, GB' },
  { id: 'rome_it', name: 'Rome, IT' },
  { id: 'madrid_es', name: 'Madrid, ES' },
  { id: 'lisbon_pt', name: 'Lisbon, PT' },
  { id: 'athens_gr', name: 'Athens, GR' },
  { id: 'amsterdam_nl', name: 'Amsterdam, NL' },
];

interface Props {
  searchParams: Promise<{ city?: string }>;
}

export default async function ForecastPage({ searchParams }: Props) {
  const resolvedParams = await searchParams;
  const selectedCity = resolvedParams.city || 'stockholm_se';
  const forecast = await fetchCityForecast(selectedCity);

  const currentCityObj = ALL_CITIES.find(c => c.id === selectedCity) || ALL_CITIES[0];

  return (
    <main className="min-h-screen p-6 md:p-12 lg:p-20">
      <div className="max-w-7xl mx-auto space-y-12">
        
        {/* Hero Section */}
        <header className="flex flex-col items-center md:items-start text-center md:text-left space-y-6 mt-4">
          <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full bg-purple-500/10 border border-purple-500/20 text-xs font-semibold text-purple-400 tracking-wide uppercase">
            <span className="w-2 h-2 rounded-full bg-purple-400 animate-pulse"></span>
            Multi-Output Random Forest Simulation
          </div>
          <h1 className="text-5xl md:text-7xl font-black tracking-tight text-slate-100">
            AI Tipping Forecast
          </h1>
          <p className="text-lg md:text-xl text-slate-400 max-w-2xl font-medium">
            Simulating 3-day future climate tipping risks with 95% confidence intervals calibrated across decision tree estimators.
          </p>
        </header>

        {/* Interactive City Selector Bar */}
        <div className="glass-panel rounded-2xl p-4 flex flex-wrap gap-2 items-center justify-center md:justify-start border border-white/5 shadow-xl">
          <span className="text-xs font-bold uppercase tracking-widest text-slate-500 mr-2 ml-2">Select Region:</span>
          {ALL_CITIES.map((c) => {
            const isSelected = c.id === selectedCity;
            return (
              <Link
                key={c.id}
                href={`/forecast?city=${c.id}`}
                className={`px-4 py-2 rounded-xl text-sm font-semibold transition-all ${
                  isSelected
                    ? 'bg-cyan-500 text-slate-950 shadow-[0_0_20px_rgba(6,182,212,0.4)] font-bold'
                    : 'bg-slate-800/60 text-slate-300 hover:bg-slate-700/60 hover:text-white border border-slate-700/40'
                }`}
              >
                {c.name}
              </Link>
            );
          })}
        </div>

        {!forecast ? (
          <div className="glass-panel rounded-2xl p-12 text-center mt-12">
            <h2 className="text-2xl font-semibold mb-4 text-slate-200">Forecast Unavailable</h2>
            <p className="text-slate-400">Unable to retrieve ML model inference for {currentCityObj.name}. Verify backend connection.</p>
          </div>
        ) : (
          <div className="space-y-12">
            
            {/* Top Overview Cards */}
            <div className="grid grid-cols-1 md:grid-cols-4 gap-6">
              
              {/* Total Estimated Score */}
              <div className="glass-panel rounded-2xl p-6 flex flex-col justify-between border-t-2 border-t-cyan-400 relative overflow-hidden group">
                <div className="absolute top-0 right-0 w-32 h-32 bg-cyan-500/10 rounded-full blur-2xl pointer-events-none"></div>
                <span className="text-xs font-bold uppercase tracking-widest text-slate-400 mb-4">Est. Total Risk (Day +3)</span>
                <div>
                  <div className="flex items-baseline gap-2">
                    <span className={`text-5xl font-black tracking-tight ${
                      forecast.estimated_total_tipping_score > 70 ? 'score-high' : forecast.estimated_total_tipping_score > 40 ? 'score-medium' : 'score-low'
                    }`}>
                      {forecast.estimated_total_tipping_score.toFixed(1)}
                    </span>
                    <span className="text-sm font-bold text-slate-500">/ 100</span>
                  </div>
                  <div className="mt-3 inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-slate-800/60 border border-slate-700/50 text-[11px] font-semibold text-slate-300">
                    95% CI: <span className="text-cyan-400 font-bold">[{forecast.total_ci_lower} - {forecast.total_ci_upper}]</span> (±{forecast.total_confidence_margin})
                  </div>
                </div>
              </div>

              {/* Forecasted Primary Driver */}
              <div className="glass-panel rounded-2xl p-6 flex flex-col justify-between">
                <span className="text-xs font-bold uppercase tracking-widest text-slate-400 mb-4">Forecasted Driver</span>
                <div>
                  <span className="text-3xl font-black text-transparent bg-clip-text bg-gradient-to-r from-cyan-400 to-blue-500 tracking-wide block mb-2">
                    {forecast.forecast_primary_driver}
                  </span>
                  <p className="text-xs text-slate-400 font-medium">
                    Meteorological factor projecting the highest severe tipping anomaly.
                  </p>
                </div>
              </div>

              {/* Baseline Tipping Score */}
              <div className="glass-panel rounded-2xl p-6 flex flex-col justify-between">
                <span className="text-xs font-bold uppercase tracking-widest text-slate-400 mb-4">Today's Baseline (t0)</span>
                <div>
                  <div className="flex items-baseline gap-2 mb-2">
                    <span className="text-4xl font-black text-slate-200">
                      {forecast.current_tipping_score.toFixed(1)}
                    </span>
                    <span className="text-sm font-bold text-slate-500">/ 100</span>
                  </div>
                  <div className="text-xs font-semibold text-slate-400 flex items-center gap-1">
                    {forecast.estimated_total_tipping_score > forecast.current_tipping_score ? (
                      <span className="text-red-400 flex items-center gap-1">▲ Projected increase of {(forecast.estimated_total_tipping_score - forecast.current_tipping_score).toFixed(1)}</span>
                    ) : (
                      <span className="text-green-400 flex items-center gap-1">▼ Projected decrease of {(forecast.current_tipping_score - forecast.estimated_total_tipping_score).toFixed(1)}</span>
                    )}
                  </div>
                </div>
              </div>

              {/* 3-Day Weather Trajectory */}
              <div className="glass-panel rounded-2xl p-6 flex flex-col justify-between bg-gradient-to-br from-slate-900/90 to-slate-800/90 border border-white/10">
                <span className="text-xs font-bold uppercase tracking-widest text-slate-300 mb-3 flex items-center justify-between">
                  <span>3-Day Weather Trajectory</span>
                  <span className="text-[10px] text-cyan-400 font-semibold bg-cyan-500/10 px-2 py-0.5 rounded">Open-Meteo</span>
                </span>
                <div className="space-y-2 text-xs font-medium text-slate-300">
                  <div className="flex justify-between items-center py-1 border-b border-white/5">
                    <span className="text-slate-400">Tomorrow (Day +1):</span>
                    <span className="font-bold text-white">{forecast.weather_trajectory_3d.temp_max_plus_1d.toFixed(1)}°C</span>
                  </div>
                  <div className="flex justify-between items-center py-1 border-b border-white/5">
                    <span className="text-slate-400">Day +2 Max Temp:</span>
                    <span className="font-bold text-white">{forecast.weather_trajectory_3d.temp_max_plus_2d.toFixed(1)}°C</span>
                  </div>
                  <div className="flex justify-between items-center py-1 border-b border-white/5">
                    <span className="text-slate-400">Day +3 Max Temp:</span>
                    <span className="font-bold text-white">{forecast.weather_trajectory_3d.temp_max_plus_3d.toFixed(1)}°C</span>
                  </div>
                  <div className="flex justify-between items-center py-1">
                    <span className="text-slate-400">Day +3 Storm Risk:</span>
                    <span className="font-bold text-cyan-400">{forecast.weather_trajectory_3d.precip_plus_3d.toFixed(1)} mm</span>
                  </div>
                </div>
              </div>

            </div>

            {/* Sub-Scores Forecast Grid */}
            <section className="space-y-6">
              <div className="flex items-center justify-between border-b border-white/5 pb-4">
                <h2 className="text-2xl font-bold tracking-tight text-slate-100">
                  Granular Multi-Output Sub-Scores
                </h2>
                <span className="text-xs font-semibold text-slate-400">
                  95% Confidence Intervals derived from tree estimator variance
                </span>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                
                {/* Helper function to render card */}
                {[
                  { title: 'Heat Score Forecast', key: 'heat_score', icon: '🌡️', desc: 'Predicting severe maximum temperature anomalies and upward thermal velocity.' },
                  { title: 'Wind Score Forecast', key: 'wind_score', icon: '💨', desc: 'Predicting severe wind gust velocity exceeding 40 km/h baseline thresholds.' },
                  { title: 'Rain Score Forecast', key: 'rain_score', icon: '🌧️', desc: 'Predicting severe 24-hour accumulated precipitation totals.' },
                  { title: 'Air Quality Forecast', key: 'air_score', icon: '🌫️', desc: 'Predicting European AQI spikes based on atmospheric stagnation.' },
                  { title: 'River Flood Forecast', key: 'river_score', icon: '🌊', desc: 'Predicting positive hydrological discharge velocity for monitored river basins.' },
                ].map((item) => {
                  const subData = forecast.sub_scores_forecast[item.key as keyof typeof forecast.sub_scores_forecast];
                  const score = subData.estimated_score;
                  let colorClass = 'score-low';
                  let barColor = 'bg-green-500';
                  if (score > 70) {
                    colorClass = 'score-high';
                    barColor = 'bg-red-500';
                  } else if (score > 40) {
                    colorClass = 'score-medium';
                    barColor = 'bg-amber-500';
                  }

                  return (
                    <div key={item.key} className="glass-card rounded-2xl p-6 flex flex-col justify-between space-y-6 relative overflow-hidden group">
                      <div>
                        <div className="flex items-center justify-between mb-2">
                          <h3 className="text-lg font-bold text-slate-100 flex items-center gap-2">
                            <span>{item.icon}</span> {item.title}
                          </h3>
                        </div>
                        <p className="text-xs text-slate-400 font-medium leading-relaxed">
                          {item.desc}
                        </p>
                      </div>

                      <div className="space-y-4">
                        <div className="flex items-end justify-between">
                          <span className="text-[11px] font-bold text-slate-500 uppercase tracking-widest">
                            Est. Score
                          </span>
                          <span className={`text-4xl font-black tracking-tight ${colorClass}`}>
                            {score.toFixed(1)}
                          </span>
                        </div>

                        {/* Confidence Interval Pill */}
                        <div className="flex items-center justify-between p-2.5 rounded-xl bg-slate-800/40 border border-slate-700/40 text-xs">
                          <span className="text-slate-400 font-medium">95% Confidence Interval</span>
                          <span className="font-bold text-slate-200">
                            [{subData.ci_lower} - {subData.ci_upper}] <span className="text-slate-500 font-normal">(±{subData.confidence_margin})</span>
                          </span>
                        </div>

                        {/* Visual Uncertainty Progress Bar */}
                        <div className="space-y-1">
                          <div className="w-full h-2 bg-slate-800 rounded-full overflow-hidden relative">
                            {/* Base estimated score bar */}
                            <div className={`h-full ${barColor} transition-all duration-500`} style={{ width: `${score}%` }} />
                            {/* Uncertainty overlay indication */}
                            <div 
                              className="absolute top-0 h-full bg-white/20 backdrop-blur-sm transition-all duration-500 border-x border-white/40" 
                              style={{ 
                                left: `${subData.ci_lower}%`, 
                                width: `${subData.ci_upper - subData.ci_lower}%` 
                              }} 
                            />
                          </div>
                          <div className="flex justify-between text-[10px] font-semibold text-slate-500">
                            <span>0 (Stable)</span>
                            <span>Uncertainty Margin: ±{subData.confidence_margin.toFixed(1)}</span>
                            <span>100 (Severe)</span>
                          </div>
                        </div>

                      </div>
                    </div>
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
