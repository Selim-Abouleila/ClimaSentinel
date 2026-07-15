"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useSyncExternalStore } from "react";

const subscribeToHostname = () => () => undefined;
const getHostnameSnapshot = () => window.location.hostname.includes("staging");
const getServerHostnameSnapshot = () => false;

export default function Navigation() {
  const pathname = usePathname();
  const isForecast = pathname?.startsWith("/forecast");
  const isDashboard = !isForecast;
  const isStaging = useSyncExternalStore(
    subscribeToHostname,
    getHostnameSnapshot,
    getServerHostnameSnapshot,
  );

  return (
    <header className="app-navigation">
      <div className="app-navigation__inner">
        <Link href="/" className="brand" aria-label="ClimaSentinel overview">
          <span className="brand__name">
            <span>Clima</span><strong>Sentinel</strong>
          </span>
          {isStaging && (
            <span className="brand__environment">
              STAGING
            </span>
          )}
        </Link>

        <nav className="app-navigation__links" aria-label="Primary navigation">
          <Link 
            href="/" 
            className={`app-navigation__link ${isDashboard ? 'is-active' : ''}`}
            aria-current={isDashboard ? "page" : undefined}
          >
            Overview
          </Link>

          <Link 
            href="/forecast" 
            className={`app-navigation__link ${isForecast ? 'is-active' : ''}`}
            aria-current={isForecast ? "page" : undefined}
          >
            3-day forecast
          </Link>
        </nav>
      </div>
    </header>
  );
}
