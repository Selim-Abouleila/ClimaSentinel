import type { CityScore, SignalStatus } from '@/lib/api';

export interface NormalizedSignalReading {
  score: number | null;
  status: SignalStatus;
  monitored: boolean;
  available: boolean;
  coverage: number | null;
}

export interface SnapshotFreshness {
  ingestedAt: Date;
  ageHours: number;
  stale: boolean;
}

export const SNAPSHOT_STALE_AFTER_HOURS = 36;

function isFiniteNumber(value: unknown): value is number {
  return typeof value === 'number' && Number.isFinite(value);
}

export function hasCurrentScore(
  city: CityScore,
): city is CityScore & { current_tipping_score: number } {
  const hasFiniteScore = isFiniteNumber(city.current_tipping_score);

  // The metadata is absent on the legacy API. Infer availability from its
  // numeric score only during the frontend-first compatibility window; once
  // the v2 API supplies an explicit false value, it always takes precedence.
  return hasFiniteScore && city.current_score_available !== false;
}

export function scoredCurrentCities(
  cities: CityScore[],
): Array<CityScore & { current_tipping_score: number }> {
  return cities.filter(hasCurrentScore);
}

export function meanCurrentScore(cities: CityScore[]): number | null {
  const scoredCities = scoredCurrentCities(cities);
  if (scoredCities.length === 0) return null;
  return scoredCities.reduce(
    (total, city) => total + city.current_tipping_score,
    0,
  ) / scoredCities.length;
}

export function hasPartialFactorCoverage(city: CityScore): boolean {
  return hasCurrentScore(city)
    && typeof city.available_factor_count === 'number'
    && typeof city.monitored_factor_count === 'number'
    && city.available_factor_count < city.monitored_factor_count;
}

export function getSnapshotFreshness(
  timestamp: string | undefined,
  nowMs: number = Date.now(),
): SnapshotFreshness | null {
  if (!timestamp) return null;
  const ingestedAt = new Date(timestamp);
  if (Number.isNaN(ingestedAt.getTime())) return null;
  const ageHours = Math.max(0, nowMs - ingestedAt.getTime()) / 3_600_000;
  return {
    ingestedAt,
    ageHours,
    stale: ageHours > SNAPSHOT_STALE_AFTER_HOURS,
  };
}

export function normalizeSignalReading(
  score: number | null,
  status: SignalStatus | undefined,
  monitored: boolean | undefined,
  available: boolean | undefined,
  coverage: number | null | undefined,
): NormalizedSignalReading {
  const hasValidScore = isFiniteNumber(score);
  const safeCoverage = isFiniteNumber(coverage)
    ? Math.min(1, Math.max(0, coverage))
    : null;

  if (status === 'not_monitored') {
    return {
      score: null,
      status: 'not_monitored',
      monitored: false,
      available: false,
      coverage: null,
    };
  }

  const explicitlyAvailable = status === 'available'
    && monitored !== false
    && available !== false
    && hasValidScore
    && safeCoverage === 1;
  const legacyAvailable = status === undefined && hasValidScore;

  if (explicitlyAvailable || legacyAvailable) {
    return {
      score,
      status: 'available',
      monitored: true,
      available: true,
      coverage: safeCoverage,
    };
  }

  return {
    score: null,
    status: 'unavailable',
    monitored: true,
    available: false,
    coverage: safeCoverage,
  };
}
