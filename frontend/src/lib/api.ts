const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8000';

export interface CityScore {
  operational_ingestion_run_id?: string;
  operational_ingested_at_utc?: string;
  city_id: string;
  current_tipping_score: number | null;
  current_primary_driver: string | null;
  // Optional during the expand/contract rollout so this frontend can be
  // deployed before the v2 backend contract without hiding legacy scores.
  current_score_available?: boolean;
  monitored_factor_count?: number;
  available_factor_count?: number;
  overall_coverage?: number | null;
  rank: number;
}

export type SignalStatus = 'available' | 'not_monitored' | 'unavailable';

export interface CityDetail {
  operational_ingestion_run_id?: string;
  operational_ingested_at_utc?: string;
  city_id: string;
  score_date?: string;
  current_tipping_score: number | null;
  current_primary_driver: string | null;
  current_score_available?: boolean;
  monitored_factor_count?: number;
  available_factor_count?: number;
  overall_coverage?: number | null;
  // Scores remain null unless the signal is available for the current window.
  heat_score: number | null;
  heat_status?: SignalStatus;
  heat_monitored?: boolean;
  heat_available?: boolean;
  heat_coverage?: number | null;
  wind_score: number | null;
  wind_status?: SignalStatus;
  wind_monitored?: boolean;
  wind_available?: boolean;
  wind_coverage?: number | null;
  rain_score: number | null;
  rain_status?: SignalStatus;
  rain_monitored?: boolean;
  rain_available?: boolean;
  rain_coverage?: number | null;
  air_score: number | null;
  air_status?: SignalStatus;
  air_monitored?: boolean;
  air_available?: boolean;
  air_coverage?: number | null;
  river_score: number | null;
  river_status?: SignalStatus;
  river_monitored?: boolean;
  river_available?: boolean;
  river_coverage?: number | null;
}

export async function fetchCurrentScores(): Promise<CityScore[]> {
  try {
    const res = await fetch(`${API_BASE_URL}/data/current-scores`, { cache: 'no-store' });
    if (!res.ok) throw new Error('Failed to fetch current scores');
    return res.json();
  } catch (error) {
    console.error(error);
    return [];
  }
}

export async function fetchCityScores(city_id: string): Promise<CityDetail | null> {
  try {
    const res = await fetch(`${API_BASE_URL}/data/city/${encodeURIComponent(city_id)}/scores`, {
      cache: 'no-store',
    });
    if (res.status === 404) return null;
    if (!res.ok) throw new Error(`Failed to fetch scores for ${city_id}`);
    return res.json();
  } catch (error) {
    console.error(error);
    return null;
  }
}

export type ForecastComponentMethod = 'forecast_rule';

export type ForecastValidationStatus =
  | 'era5_backtested_limited'
  | 'era5_backtested_insufficient_skill'
  | 'not_observation_validated';

export type ForecastUncertaintyMethod = 'none';

export interface SubScoreForecast {
  estimated_score: number | null;
  ci_lower: null;
  ci_upper: null;
  confidence_margin: null;
  available: boolean;
  method: ForecastComponentMethod;
  validation_status: ForecastValidationStatus;
  uncertainty_method: ForecastUncertaintyMethod;
  provenance: string;
  method_reason: string;
  unavailable_reason: string | null;
}

export interface CityForecast {
  city_id: string;
  horizon_days: number;
  prediction_date: string;
  prediction_source: 'same_vintage_forecast_rules';
  model_version: null;
  forecast_method: 'forecast_rules_baseline';
  model_target_components: [];
  rule_based_components: string[];
  feature_schema_version: string;
  feature_ingestion_run_id: string;
  feature_ingested_at_utc: string;
  forecast_origin_time_zone: string;
  current_tipping_score: number;
  estimated_total_tipping_score: number;
  total_confidence_margin: null;
  total_ci_lower: null;
  total_ci_upper: null;
  total_uncertainty_method: ForecastUncertaintyMethod;
  forecast_primary_driver: string;
  forecast_primary_driver_method: ForecastComponentMethod;
  sub_scores_forecast: {
    heat_score: SubScoreForecast;
    wind_score: SubScoreForecast;
    rain_score: SubScoreForecast;
    air_score: SubScoreForecast;
    river_score: SubScoreForecast;
  };
  weather_trajectory: Record<string, number | null>;
}

export async function fetchCityForecast(city_id: string, horizonDays: number = 3): Promise<CityForecast | null> {
  try {
    const res = await fetch(`${API_BASE_URL}/data/city/${encodeURIComponent(city_id)}/forecast?horizon_days=${horizonDays}`, {
      cache: 'no-store',
    });
    if (res.status === 404) return null;
    if (!res.ok) throw new Error(`Failed to fetch forecast for ${city_id}`);
    return res.json();
  } catch (error) {
    console.error(error);
    return null;
  }
}
