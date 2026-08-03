import { expect, test } from '@playwright/test';

import type { CityScore } from '../../src/lib/api';
import {
  getSnapshotFreshness,
  hasCurrentScore,
  hasPartialFactorCoverage,
  meanCurrentScore,
  normalizeSignalReading,
  scoredCurrentCities,
} from '../../src/lib/signal-availability';

function city(
  cityId: string,
  score: number | null,
  available?: boolean,
): CityScore {
  return {
    city_id: cityId,
    current_tipping_score: score,
    current_primary_driver: score === null ? 'Unavailable' : 'Heat',
    current_score_available: available,
    rank: 1,
  };
}

test('keeps a legacy numeric score visible during frontend-first rollout', () => {
  expect(hasCurrentScore(city('paris_fr', 42.5))).toBe(true);
});

test('explicit v2 unavailability overrides even a contradictory numeric value', () => {
  expect(hasCurrentScore(city('paris_fr', 0, false))).toBe(false);
});

test('excludes unavailable cities from aggregates without dividing by zero', () => {
  const mixed = [city('paris_fr', 80, true), city('stockholm_se', null, false)];
  expect(scoredCurrentCities(mixed).map((item) => item.city_id)).toEqual(['paris_fr']);
  expect(meanCurrentScore(mixed)).toBe(80);
  expect(meanCurrentScore([city('stockholm_se', null, false)])).toBeNull();
});

test('surfaces partial factor coverage even when the available score is zero', () => {
  const partial = {
    ...city('stockholm_se', 0, true),
    monitored_factor_count: 4,
    available_factor_count: 1,
  };
  expect(hasPartialFactorCoverage(partial)).toBe(true);
});

test('marks a daily snapshot stale only after the 36-hour freshness SLA', () => {
  const ingestedAt = '2026-08-01T06:00:00Z';
  expect(getSnapshotFreshness(ingestedAt, Date.parse('2026-08-02T18:00:00Z'))?.stale)
    .toBe(false);
  expect(getSnapshotFreshness(ingestedAt, Date.parse('2026-08-02T18:00:01Z'))?.stale)
    .toBe(true);
});

test('preserves an available measured zero as a Stable-eligible score', () => {
  expect(normalizeSignalReading(0, 'available', true, true, 1)).toEqual({
    score: 0,
    status: 'available',
    monitored: true,
    available: true,
    coverage: 1,
  });
});

test('never turns unavailable AQ or unmonitored River into zero', () => {
  expect(normalizeSignalReading(null, 'unavailable', true, false, 0.5)).toEqual({
    score: null,
    status: 'unavailable',
    monitored: true,
    available: false,
    coverage: 0.5,
  });
  expect(normalizeSignalReading(0, 'not_monitored', false, false, null)).toEqual({
    score: null,
    status: 'not_monitored',
    monitored: false,
    available: false,
    coverage: null,
  });
  expect(normalizeSignalReading(0, 'available', true, true, 0.5)).toEqual({
    score: null,
    status: 'unavailable',
    monitored: true,
    available: false,
    coverage: 0.5,
  });
});
