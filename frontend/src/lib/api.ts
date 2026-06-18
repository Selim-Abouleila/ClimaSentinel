const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8000';

export interface CityScore {
  city_id: string;
  current_tipping_score: number;
  current_primary_driver: string;
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
