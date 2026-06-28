"use client";

import { useState } from "react";
import { CityForecast } from "@/lib/api";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";

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

export default function ForecastPage() {
  const [selectedCity, setSelectedCity] = useState<string | null>(null);
  const [forecast, setForecast] = useState<CityForecast | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(false);

  const handleCityClick = async (cityId: string) => {
    setSelectedCity(cityId);
    setForecast(null);
    setError(false);
    setLoading(true);

    try {
      const res = await fetch(
        `${API_BASE_URL}/data/city/${encodeURIComponent(cityId)}/forecast`,
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

  const currentCityObj = ALL_CITIES.find((c) => c.id === selectedCity);

  return (
    <main className="min-h-screen p-6 md:p-12 lg:p-20">
      <div className="max-w-7xl mx-auto space-y-12">
        {/* Hero Section */}
        <header className="flex flex-col items-center md:items-start text-center md:text-left space-y-4 mt-4">
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-slate-900 border border-slate-800 text-xs font-medium text-slate-400 tracking-wider uppercase">
            <span className="w-1.5 h-1.5 rounded-full bg-cyan-400 animate-pulse"></span>
            Multi-Output Random Forest Simulation
          </div>
          <h1 className="text-5xl md:text-6xl font-extrabold tracking-tight text-slate-100">
            AI Tipping Forecast
          </h1>
          <p className="text-base md:text-lg text-slate-400 max-w-2xl font-normal">
            Simulating 3-day future climate tipping risks with 95% confidence
            intervals calibrated across decision tree estimators.
          </p>
        </header>

        {/* Interactive City Selector Bar */}
        <div className="glass-panel rounded-xl p-3 flex flex-wrap gap-2 items-center justify-center md:justify-start border border-white/5 shadow-lg">
          <span className="text-xs font-semibold uppercase tracking-wider text-slate-500 mr-2 ml-2">
            Region:
          </span>
          {ALL_CITIES.map((c) => {
            const isSelected = c.id === selectedCity;
            return (
              <button
                key={c.id}
                onClick={() => handleCityClick(c.id)}
                disabled={loading}
                className={`px-4 py-1.5 rounded-lg text-sm transition-all ${
                  isSelected
                    ? "bg-cyan-500 text-slate-950 font-semibold shadow-[0_0_15px_rgba(6,182,212,0.3)]"
                    : "bg-slate-900/50 text-slate-400 hover:bg-slate-800 hover:text-slate-200 border border-slate-800/80"
                } ${loading ? "opacity-60 cursor-wait" : "cursor-pointer"}`}
              >
                {c.name}
              </button>
            );
          })}
        </div>

        {/* State: No City Selected */}
        {!selectedCity && (
          <div className="glass-panel rounded-xl p-16 text-center border border-white/5">
            <div className="text-4xl mb-4 text-slate-600">
              <svg xmlns="http://www.w3.org/2000/svg" className="w-12 h-12 mx-auto mb-4 text-slate-600" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M15 10.5a3 3 0 1 1-6 0 3 3 0 0 1 6 0Z" />
                <path strokeLinecap="round" strokeLinejoin="round" d="M19.5 10.5c0 7.142-7.5 11.25-7.5 11.25S4.5 17.642 4.5 10.5a7.5 7.5 0 1 1 15 0Z" />
              </svg>
            </div>
            <h2 className="text-xl font-medium text-slate-300 mb-2">
              Select a Region
            </h2>
            <p className="text-sm text-slate-500 max-w-md mx-auto">
              Choose a European city above to generate a real-time 3-day
              tipping risk forecast using our Multi-Output Random Forest model.
            </p>
          </div>
        )}

        {/* State: Loading */}
        {loading && selectedCity && (
          <div className="glass-panel rounded-xl p-16 text-center border border-white/5">
            <div className="flex flex-col items-center gap-6">
              {/* Animated spinner */}
              <div className="relative w-16 h-16">
                <div className="absolute inset-0 rounded-full border-2 border-slate-800"></div>
                <div className="absolute inset-0 rounded-full border-2 border-t-cyan-400 animate-spin"></div>
              </div>
              <div>
                <h2 className="text-xl font-medium text-slate-200 mb-2">
                  Calculating Forecast
                </h2>
                <p className="text-sm text-slate-500 max-w-md mx-auto">
                  Running real-time inference for{" "}
                  <span className="text-cyan-400 font-medium">
                    {currentCityObj?.name}
                  </span>{" "}
                  across 100 decision tree estimators and computing 95%
                  confidence intervals.
                </p>
              </div>
            </div>
          </div>
        )}

        {/* State: Error */}
        {error && !loading && selectedCity && (
          <div className="glass-panel rounded-xl p-12 text-center border border-white/5">
            <h2 className="text-xl font-medium mb-2 text-slate-300">
              Forecast Unavailable
            </h2>
            <p className="text-sm text-slate-500">
              Unable to retrieve ML model inference for{" "}
              {currentCityObj?.name}. Verify backend connection.
            </p>
          </div>
        )}

        {/* State: Results */}
        {forecast && !loading && (
          <div className="space-y-12">
            {/* Top Overview Cards */}
            <div className="grid grid-cols-1 md:grid-cols-4 gap-6">
              {/* Total Estimated Score */}
              <div className="glass-panel rounded-xl p-6 flex flex-col justify-between border border-white/5 relative overflow-hidden">
                <span className="text-xs font-semibold uppercase tracking-wider text-slate-400 mb-4">
                  Est. Total Risk (Day +3)
                </span>
                <div>
                  <div className="flex items-baseline gap-2">
                    <span
                      className={`text-5xl font-black tracking-tight ${
                        forecast.estimated_total_tipping_score > 70
                          ? "score-high"
                          : forecast.estimated_total_tipping_score > 40
                          ? "score-medium"
                          : "score-low"
                      }`}
                    >
                      {forecast.estimated_total_tipping_score.toFixed(1)}
                    </span>
                    <span className="text-sm font-medium text-slate-500">
                      / 100
                    </span>
                  </div>
                  <div className="mt-3 inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-slate-900 border border-slate-800 text-[11px] font-medium text-slate-400">
                    95% CI:{" "}
                    <span className="text-cyan-400 font-semibold">
                      [{forecast.total_ci_lower} - {forecast.total_ci_upper}]
                    </span>{" "}
                    (±{forecast.total_confidence_margin})
                  </div>
                </div>
              </div>

              {/* Forecasted Primary Driver */}
              <div className="glass-panel rounded-xl p-6 flex flex-col justify-between border border-white/5">
                <span className="text-xs font-semibold uppercase tracking-wider text-slate-400 mb-4">
                  Forecasted Driver
                </span>
                <div>
                  <span className="text-3xl font-bold text-slate-100 tracking-wide block mb-2">
                    {forecast.forecast_primary_driver}
                  </span>
                  <p className="text-xs text-slate-500 font-normal leading-relaxed">
                    Meteorological factor projecting the highest severe tipping
                    anomaly.
                  </p>
                </div>
              </div>

              {/* Baseline Tipping Score */}
              <div className="glass-panel rounded-xl p-6 flex flex-col justify-between border border-white/5">
                <span className="text-xs font-semibold uppercase tracking-wider text-slate-400 mb-4">
                  Today&apos;s Baseline (t0)
                </span>
                <div>
                  <div className="flex items-baseline gap-2 mb-2">
                    <span className="text-4xl font-extrabold text-slate-200">
                      {forecast.current_tipping_score.toFixed(1)}
                    </span>
                    <span className="text-sm font-medium text-slate-500">
                      / 100
                    </span>
                  </div>
                  <div className="text-xs font-medium text-slate-400 flex items-center gap-1">
                    {forecast.estimated_total_tipping_score >
                    forecast.current_tipping_score ? (
                      <span className="text-amber-400">
                        Projected increase of{" "}
                        {(
                          forecast.estimated_total_tipping_score -
                          forecast.current_tipping_score
                        ).toFixed(1)}
                      </span>
                    ) : (
                      <span className="text-emerald-400">
                        Projected decrease of{" "}
                        {(
                          forecast.current_tipping_score -
                          forecast.estimated_total_tipping_score
                        ).toFixed(1)}
                      </span>
                    )}
                  </div>
                </div>
              </div>

              {/* 3-Day Weather Trajectory */}
              <div className="glass-panel rounded-xl p-6 flex flex-col justify-between bg-slate-900/60 border border-white/5">
                <span className="text-xs font-semibold uppercase tracking-wider text-slate-400 mb-3 flex items-center justify-between">
                  <span>3-Day Weather Trajectory</span>
                  <span className="text-[10px] text-cyan-400 font-medium bg-cyan-500/10 px-2 py-0.5 rounded border border-cyan-500/20">
                    Open-Meteo
                  </span>
                </span>
                <div className="space-y-2 text-xs font-normal text-slate-400">
                  <div className="flex justify-between items-center py-1 border-b border-white/5">
                    <span>Tomorrow (Day +1):</span>
                    <span className="font-medium text-slate-200">
                      {forecast.weather_trajectory_3d.temp_max_plus_1d.toFixed(1)}
                      °C
                    </span>
                  </div>
                  <div className="flex justify-between items-center py-1 border-b border-white/5">
                    <span>Day +2 Max Temp:</span>
                    <span className="font-medium text-slate-200">
                      {forecast.weather_trajectory_3d.temp_max_plus_2d.toFixed(1)}
                      °C
                    </span>
                  </div>
                  <div className="flex justify-between items-center py-1 border-b border-white/5">
                    <span>Day +3 Max Temp:</span>
                    <span className="font-medium text-slate-200">
                      {forecast.weather_trajectory_3d.temp_max_plus_3d.toFixed(1)}
                      °C
                    </span>
                  </div>
                  <div className="flex justify-between items-center py-1">
                    <span>Day +3 Storm Risk:</span>
                    <span className="font-medium text-cyan-400">
                      {forecast.weather_trajectory_3d.precip_plus_3d.toFixed(1)}{" "}
                      mm
                    </span>
                  </div>
                </div>
              </div>
            </div>

            {/* Sub-Scores Forecast Grid */}
            <section className="space-y-6">
              <div className="flex items-center justify-between border-b border-white/5 pb-4">
                <h2 className="text-xl font-bold tracking-tight text-slate-200">
                  Granular Multi-Output Sub-Scores
                </h2>
                <span className="text-xs font-medium text-slate-500">
                  95% Confidence Intervals derived from tree estimator variance
                </span>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                {[
                  {
                    title: "Heat Score Forecast",
                    key: "heat_score",
                    desc: "Predicting severe maximum temperature anomalies and upward thermal velocity.",
                  },
                  {
                    title: "Wind Score Forecast",
                    key: "wind_score",
                    desc: "Predicting severe wind gust velocity exceeding 40 km/h baseline thresholds.",
                  },
                  {
                    title: "Rain Score Forecast",
                    key: "rain_score",
                    desc: "Predicting severe 24-hour accumulated precipitation totals.",
                  },
                  {
                    title: "Air Quality Forecast",
                    key: "air_score",
                    desc: "Predicting European AQI spikes based on atmospheric stagnation.",
                  },
                  {
                    title: "River Flood Forecast",
                    key: "river_score",
                    desc: "Predicting positive hydrological discharge velocity for monitored river basins.",
                  },
                ].map((item) => {
                  const subData =
                    forecast.sub_scores_forecast[
                      item.key as keyof typeof forecast.sub_scores_forecast
                    ];
                  const score = subData.estimated_score;
                  let colorClass = "score-low";
                  let barColor = "bg-emerald-500";
                  if (score > 70) {
                    colorClass = "score-high";
                    barColor = "bg-rose-500";
                  } else if (score > 40) {
                    colorClass = "score-medium";
                    barColor = "bg-amber-500";
                  }

                  return (
                    <div
                      key={item.key}
                      className="glass-card rounded-xl p-6 flex flex-col justify-between space-y-6 border border-white/5 relative overflow-hidden"
                    >
                      <div>
                        <h3 className="text-base font-semibold text-slate-200 mb-1.5">
                          {item.title}
                        </h3>
                        <p className="text-xs text-slate-500 font-normal leading-relaxed">
                          {item.desc}
                        </p>
                      </div>

                      <div className="space-y-4">
                        <div className="flex items-end justify-between">
                          <span className="text-[11px] font-semibold text-slate-500 uppercase tracking-wider">
                            Est. Score
                          </span>
                          <span
                            className={`text-4xl font-bold tracking-tight ${colorClass}`}
                          >
                            {score.toFixed(1)}
                          </span>
                        </div>

                        {/* Confidence Interval Pill */}
                        <div className="flex items-center justify-between p-2.5 rounded-lg bg-slate-900/60 border border-slate-800/80 text-xs">
                          <span className="text-slate-400 font-normal">
                            95% Confidence Interval
                          </span>
                          <span className="font-semibold text-slate-200">
                            [{subData.ci_lower} - {subData.ci_upper}]{" "}
                            <span className="text-slate-500 font-normal">
                              (±{subData.confidence_margin})
                            </span>
                          </span>
                        </div>

                        {/* Visual Uncertainty Progress Bar */}
                        <div className="space-y-1.5">
                          <div className="w-full h-1.5 bg-slate-900 rounded-full overflow-hidden relative">
                            <div
                              className={`h-full ${barColor} transition-all duration-500`}
                              style={{ width: `${score}%` }}
                            />
                            <div
                              className="absolute top-0 h-full bg-white/20 backdrop-blur-sm transition-all duration-500 border-x border-white/40"
                              style={{
                                left: `${subData.ci_lower}%`,
                                width: `${subData.ci_upper - subData.ci_lower}%`,
                              }}
                            />
                          </div>
                          <div className="flex justify-between text-[10px] font-medium text-slate-500">
                            <span>0 (Stable)</span>
                            <span>
                              Uncertainty Margin: ±
                              {subData.confidence_margin.toFixed(1)}
                            </span>
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
