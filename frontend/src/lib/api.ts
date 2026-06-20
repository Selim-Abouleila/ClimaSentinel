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
