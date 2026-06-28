const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8000';

export interface CityScore {
  city_id: string;
  current_tipping_score: number;
  current_primary_driver: string;
}

export interface CityDetail {
  city_id: string;
  current_tipping_score: number;
  current_primary_driver: string;
  // Individual sub-scores (0–100)
  heat_score: number;
  wind_score: number;
  rain_score: number;
  air_score: number;
  river_score: number;
}

export async function fetchCurrentScores(): Promise<CityScore[]> {
  try {
    const res = await fetch(`${API_BASE_URL}/data/current-scores?limit=10`, { cache: 'no-store' });
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

export interface SubScoreForecast {
  estimated_score: number;
  ci_lower: number;
  ci_upper: number;
  confidence_margin: number;
}

export interface CityForecast {
  city_id: string;
  prediction_date: string;
  current_tipping_score: number;
  estimated_total_tipping_score: number;
  total_confidence_margin: number;
  total_ci_lower: number;
  total_ci_upper: number;
  forecast_primary_driver: string;
  sub_scores_forecast: {
    heat_score: SubScoreForecast;
    wind_score: SubScoreForecast;
    rain_score: SubScoreForecast;
    air_score: SubScoreForecast;
    river_score: SubScoreForecast;
  };
  weather_trajectory_3d: {
    temp_max_plus_1d: number;
    temp_max_plus_2d: number;
    temp_max_plus_3d: number;
    precip_plus_3d: number;
    wind_plus_3d: number;
  };
}

export async function fetchCityForecast(city_id: string): Promise<CityForecast | null> {
  try {
    const res = await fetch(`${API_BASE_URL}/data/city/${encodeURIComponent(city_id)}/forecast`, {
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
