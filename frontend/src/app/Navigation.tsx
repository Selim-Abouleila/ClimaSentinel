"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

export default function Navigation() {
  const pathname = usePathname();
  const isForecast = pathname?.startsWith("/forecast");
  const isDashboard = !isForecast;

  return (
    <header className="sticky top-0 z-50 glass-panel border-b border-white/5 px-6 py-3.5 shadow-lg backdrop-blur-md bg-slate-950/80">
      <div className="max-w-7xl mx-auto flex items-center justify-between">
        {/* Slightly bigger ClimaSentinel logo */}
        <Link href="/" className="flex items-center gap-2 group transition-opacity hover:opacity-80">
          <span className="font-black text-2xl md:text-3xl tracking-wider text-transparent bg-clip-text bg-gradient-to-r from-slate-100 via-slate-200 to-slate-400">
            ClimaSentinel
          </span>
          <span className="text-[10px] font-bold tracking-widest text-cyan-400 uppercase px-2 py-0.5 rounded bg-cyan-500/10 border border-cyan-500/20">
            Staging
          </span>
        </Link>

        {/* Dynamic Nav Pills with Blue Pulsing Indicator */}
        <nav className="flex items-center gap-4 md:gap-6">
          <Link 
            href="/" 
            className={`relative px-4 py-1.5 rounded-full text-sm font-semibold transition-all flex items-center gap-2 border ${
              isDashboard 
                ? 'text-cyan-400 bg-cyan-950/60 border-cyan-500/50 shadow-[0_0_20px_rgba(6,182,212,0.25)] font-bold' 
                : 'text-slate-400 bg-slate-900/50 border-slate-800 hover:bg-slate-800/50 hover:text-slate-200'
            }`}
          >
            <span className={`w-2 h-2 rounded-full ${isDashboard ? 'bg-cyan-400 animate-pulse' : 'bg-slate-600'}`}></span>
            Live Dashboard
          </Link>

          <Link 
            href="/forecast" 
            className={`relative px-4 py-1.5 rounded-full text-sm font-semibold transition-all flex items-center gap-2 border ${
              isForecast 
                ? 'text-cyan-400 bg-cyan-950/60 border-cyan-500/50 shadow-[0_0_20px_rgba(6,182,212,0.25)] font-bold' 
                : 'text-slate-400 bg-slate-900/50 border-slate-800 hover:bg-slate-800/50 hover:text-slate-200'
            }`}
          >
            <span className={`w-2 h-2 rounded-full ${isForecast ? 'bg-cyan-400 animate-pulse' : 'bg-slate-600'}`}></span>
            AI Tipping Forecast
          </Link>
        </nav>
      </div>
    </header>
  );
}
