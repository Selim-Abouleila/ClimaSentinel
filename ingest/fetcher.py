"""
fetcher.py — Open-Meteo API client
Fetches weather forecast, air quality, river discharge, historical weather,
and climate projection data for a given city.
"""

import requests
from datetime import date, datetime, timedelta, timezone

WEATHER_API_URL     = "https://api.open-meteo.com/v1/forecast"
AIR_QUALITY_API_URL = "https://air-quality-api.open-meteo.com/v1/air-quality"
FLOOD_API_URL       = "https://flood-api.open-meteo.com/v1/flood"
HISTORICAL_API_URL  = "https://archive-api.open-meteo.com/v1/archive"
CLIMATE_API_URL     = "https://climate-api.open-meteo.com/v1/climate"


def fetch_weather_forecast(city: dict) -> list[dict]:
    """
    Fetch hourly weather forecast for the next 7 days.
    Intended cadence: once daily (cron: 0 6 * * *)
    Returns a list of flat row dicts ready for BigQuery insertion.
    """
    params = {
        "latitude":      city["latitude"],
        "longitude":     city["longitude"],
        "hourly":        "temperature_2m,precipitation,wind_speed_10m,wind_gusts_10m,weather_code",
        "timezone":      city["timezone"],
        "forecast_days": 7,   # 7 days x 24h = 168 rows per city
    }

    response = requests.get(WEATHER_API_URL, params=params, timeout=30)
    response.raise_for_status()
    data   = response.json()
    hourly = data["hourly"]
    times  = hourly["time"]

    return [
        {
            "city_id":          city["city_id"],
            "valid_ts_utc":     ts + ":00",          # ISO 8601 -> BQ TIMESTAMP
            "temperature_2m":   hourly["temperature_2m"][i],
            "precipitation_mm": hourly["precipitation"][i],
            "wind_speed_10m":   hourly["wind_speed_10m"][i],
            "wind_gusts_10m":   hourly["wind_gusts_10m"][i],
            "weather_code":     hourly["weather_code"][i],
        }
        for i, ts in enumerate(times)
    ]


def fetch_air_quality(city: dict) -> list[dict]:
    """
    Fetch hourly air quality data for the next 5 days.
    Intended cadence: once daily (cron: 0 6 * * *)
    5 days used (instead of 2) since we only ingest once per day.
    Returns a list of flat row dicts ready for BigQuery insertion.
    """
    params = {
        "latitude":      city["latitude"],
        "longitude":     city["longitude"],
        "hourly":        "european_aqi,pm2_5,pm10,nitrogen_dioxide,ozone",
        "timezone":      city["timezone"],
        "forecast_days": 5,   # 5 days x 24h = 120 rows per city
    }

    response = requests.get(AIR_QUALITY_API_URL, params=params, timeout=30)
    response.raise_for_status()
    data   = response.json()
    hourly = data["hourly"]
    times  = hourly["time"]

    return [
        {
            "city_id":      city["city_id"],
            "valid_ts_utc": ts + ":00",
            "european_aqi": hourly["european_aqi"][i],
            "pm2_5":        hourly["pm2_5"][i],
            "pm10":         hourly["pm10"][i],
            "no2":          hourly["nitrogen_dioxide"][i],
            "o3":           hourly["ozone"][i],
        }
        for i, ts in enumerate(times)
    ]


def fetch_flood_discharge(city: dict) -> list[dict]:
    """
    Fetch daily river discharge forecast for the next 7 days.
    Only meaningful for cities where river_enabled=true in cities.csv.
    The flood API returns the closest river within 5 km of the coordinates.
    Intended cadence: once daily (cron: 0 6 * * *)
    Returns a list of flat row dicts ready for BigQuery insertion.
    """
    params = {
        "latitude":      city["latitude"],
        "longitude":     city["longitude"],
        "daily":         "river_discharge",
        "forecast_days": 7,   # 7 daily rows per city
    }

    response = requests.get(FLOOD_API_URL, params=params, timeout=30)
    response.raise_for_status()
    data  = response.json()
    daily = data["daily"]

    return [
        {
            "city_id":             city["city_id"],
            "date":                daily["time"][i],    # YYYY-MM-DD string -> BQ DATE
            "river_discharge_m3s": daily["river_discharge"][i],
        }
        for i in range(len(daily["time"]))
    ]


def fetch_historical_weather(city: dict) -> list[dict]:
    """
    Fetch ERA5 reanalysis historical daily weather for the last 7 confirmed days.
    ERA5 has a ~5-day publication lag, so we use a window of today-12 to today-6
    to guarantee we always land on confirmed, non-partial data.
    Intended cadence: once daily (cron: 0 6 * * *)
    Returns a list of flat row dicts ready for BigQuery insertion.
    """
    today      = datetime.now(timezone.utc).date()
    end_date   = today - timedelta(days=6)    # safely within ERA5 publication lag
    start_date = today - timedelta(days=12)   # 7-day rolling window

    params = {
        "latitude":   city["latitude"],
        "longitude":  city["longitude"],
        "start_date": start_date.isoformat(),
        "end_date":   end_date.isoformat(),
        "daily":      "temperature_2m_mean,temperature_2m_max,temperature_2m_min,"
                      "precipitation_sum,wind_speed_10m_max",
        "timezone":   city["timezone"],
    }

    response = requests.get(HISTORICAL_API_URL, params=params, timeout=30)
    response.raise_for_status()
    data  = response.json()
    daily = data["daily"]

    return [
        {
            "city_id":              city["city_id"],
            "date":                 daily["time"][i],
            "temperature_2m_mean":  daily["temperature_2m_mean"][i],
            "temperature_2m_max":   daily["temperature_2m_max"][i],
            "temperature_2m_min":   daily["temperature_2m_min"][i],
            "precipitation_sum_mm": daily["precipitation_sum"][i],
            "wind_speed_10m_max":   daily["wind_speed_10m_max"][i],
        }
        for i in range(len(daily["time"]))
    ]


def fetch_climate_projection(city: dict) -> list[dict]:
    """
    Fetch CMIP6 (MRI-AGCM3-2-S model) daily climate projections for the next 10 years.
    Only runs on the 1st of each month to avoid accumulating identical rows daily.
    Returns [] on days 2-31 so the main loop skips silently.
    Intended cadence: monthly (guardian check: today.day == 1)
    Returns a list of flat row dicts ready for BigQuery insertion.
    """
    today = datetime.now(timezone.utc).date()

    # Guard: only ingest projections once per month
    if today.day != 1:
        return []

    start_date = today
    end_date   = date(today.year + 10, today.month, 1)

    params = {
        "latitude":   city["latitude"],
        "longitude":  city["longitude"],
        "start_date": start_date.isoformat(),
        "end_date":   end_date.isoformat(),
        "models":     "MRI_AGCM3_2_S",
        "daily":      "temperature_2m_max,temperature_2m_min,precipitation_sum,wind_speed_10m_max",
    }

    response = requests.get(CLIMATE_API_URL, params=params, timeout=90)
    response.raise_for_status()
    data  = response.json()
    daily = data["daily"]

    return [
        {
            "city_id":              city["city_id"],
            "date":                 daily["time"][i],
            "model":                "MRI_AGCM3_2_S",
            "temperature_2m_max":   daily["temperature_2m_max"][i],
            "temperature_2m_min":   daily["temperature_2m_min"][i],
            "precipitation_sum_mm": daily["precipitation_sum"][i],
            "wind_speed_10m_max":   daily["wind_speed_10m_max"][i],
        }
        for i in range(len(daily["time"]))
    ]
