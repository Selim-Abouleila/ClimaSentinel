"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";

export default function Navigation() {
  const pathname = usePathname();
  const isForecast = pathname?.startsWith("/forecast");
  const isDashboard = !isForecast;
  const [isStaging, setIsStaging] = useState<boolean>(false);

  useEffect(() => {
    if (typeof window !== "undefined") {
      setIsStaging(window.location.hostname.includes("staging"));
    }
  }, []);

  return (
    <header className="sticky top-0 z-50 glass-panel border-b border-white/5 px-6 py-3.5 shadow-lg backdrop-blur-md bg-slate-950/80">
      <div className="max-w-7xl mx-auto flex items-center justify-between">
        <Link href="/" className="flex items-center gap-2 group transition-opacity hover:opacity-80">
          <span
            className="font-black tracking-wider select-none"
            style={{
              fontSize: 'clamp(1.45rem, 2.5vw, 1.8rem)',
              background: 'linear-gradient(90deg, rgba(148,163,184,0.6) 0%, rgba(56,189,248,0.9) 25%, rgba(34,211,238,1) 50%, rgba(56,189,248,0.9) 75%, rgba(148,163,184,0.6) 100%)',
              backgroundSize: '200% 100%',
              WebkitBackgroundClip: 'text',
              backgroundClip: 'text',
              color: 'transparent',
              animation: 'waterFill 6s ease-in-out infinite',
            }}
          >
            ClimaSentinel
          </span>
          {isStaging && (
            <span className="text-[10px] font-bold tracking-widest text-cyan-400 uppercase px-2 py-0.5 rounded bg-cyan-500/10 border border-cyan-500/20">
              STAGING
            </span>
          )}
        </Link>

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
