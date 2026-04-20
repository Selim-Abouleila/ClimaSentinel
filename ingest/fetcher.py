"""
fetcher.py — Open-Meteo API client
Fetches weather forecast and air quality data for a given city.
"""

import requests

WEATHER_API_URL = "https://api.open-meteo.com/v1/forecast"
AIR_QUALITY_API_URL = "https://air-quality-api.open-meteo.com/v1/air-quality"


def fetch_weather_forecast(city: dict) -> list[dict]:
    """
    Fetch hourly weather forecast for the next 7 days.
    Intended cadence: once daily (cron: 0 6 * * *)
    Returns a list of flat row dicts ready for BigQuery insertion.
    """
    params = {
        "latitude": city["latitude"],
        "longitude": city["longitude"],
        "hourly": "temperature_2m,precipitation,wind_speed_10m,wind_gusts_10m,weather_code",
        "timezone": city["timezone"],
        "forecast_days": 7,   # 7 days × 24h = 168 rows per city
    }

    response = requests.get(WEATHER_API_URL, params=params, timeout=30)
    response.raise_for_status()
    data = response.json()

    hourly = data["hourly"]
    times = hourly["time"]

    rows = []
    for i, ts in enumerate(times):
        rows.append({
            "city_id":            city["city_id"],
            "valid_ts_utc":       ts + ":00",          # ISO 8601 → BQ TIMESTAMP
            "temperature_2m":     hourly["temperature_2m"][i],
            "precipitation_mm":   hourly["precipitation"][i],
            "wind_speed_10m":     hourly["wind_speed_10m"][i],
            "wind_gusts_10m":     hourly["wind_gusts_10m"][i],
            "weather_code":       hourly["weather_code"][i],
        })

    return rows


def fetch_air_quality(city: dict) -> list[dict]:
    """
    Fetch hourly air quality data for the next 5 days.
    Intended cadence: once daily (cron: 0 6 * * *)
    5 days used (instead of 2) since we only ingest once per day.
    Returns a list of flat row dicts ready for BigQuery insertion.
    """
    params = {
        "latitude": city["latitude"],
        "longitude": city["longitude"],
        "hourly": "european_aqi,pm2_5,pm10,nitrogen_dioxide,ozone",
        "timezone": city["timezone"],
        "forecast_days": 5,   # 5 days × 24h = 120 rows per city
    }

    response = requests.get(AIR_QUALITY_API_URL, params=params, timeout=30)
    response.raise_for_status()
    data = response.json()

    hourly = data["hourly"]
    times = hourly["time"]

    rows = []
    for i, ts in enumerate(times):
        rows.append({
            "city_id":       city["city_id"],
            "valid_ts_utc":  ts + ":00",
            "european_aqi":  hourly["european_aqi"][i],
            "pm2_5":         hourly["pm2_5"][i],
            "pm10":          hourly["pm10"][i],
            "no2":           hourly["nitrogen_dioxide"][i],
            "o3":            hourly["ozone"][i],
        })

    return rows
