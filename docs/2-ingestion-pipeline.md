# 2. Ingestion Pipeline

The ClimaSentinel ingestion pipeline is a serverless, automated data pipeline running entirely on Google Cloud Platform. It scales to zero when idle and automatically fetches daily weather, air quality, river discharge, historical reanalysis, and long-term climate projection data for a configurable set of cities directly into BigQuery.

## Architecture

The ingestion process relies on three core Google Cloud services, all provisioned via Terraform:
1. **Cloud Scheduler**: Acts as a cron job, firing an HTTP request to the Cloud Run job once a day at `06:00 UTC` (`0 6 * * *`).
2. **Cloud Run Job**: Executes the Python runner which contains the application logic to pull from APIs and transform the results.
3. **BigQuery**: Provides the data warehouse where processed, raw climate data is appended into time-partitioned tables.

Additionally, **Artifact Registry** is used to store the Docker container image built via **Cloud Build**.

## Configuration: The City List

The ingestion script iterates over 10 major European cities configured in `config/cities.csv`. To add or remove cities, simply update the CSV and push. The `river_enabled` column controls whether flood/river discharge data is fetched for that city.

| City | Country | Latitude | Longitude | River Monitoring |
|---|---|---|---|---|
| Paris | FR | 48.853 | 2.348 | ✅ |
| London | GB | 51.508 | -0.125 | — |
| Madrid | ES | 40.416 | -3.702 | — |
| Berlin | DE | 52.524 | 13.410 | — |
| Rome | IT | 41.891 | 12.511 | — |
| Amsterdam | NL | 52.374 | 4.889 | ✅ |
| Athens | GR | 37.983 | 23.727 | — |
| Warsaw | PL | 52.229 | 21.011 | ✅ |
| Lisbon | PT | 38.716 | -9.133 | — |
| Stockholm | SE | 59.329 | 18.068 | — |

---

## APIs & Data Retrieved

The Cloud Run job fetches data from **five Open-Meteo endpoints** for each city, formats it as JSON, and streams it into the `raw` BigQuery dataset. Because tables are time-partitioned, no data is overwritten — historical forecasts are accumulated continuously over time allowing for forecast deviation monitoring.

### 1. Weather Forecast (`raw.weather_forecast_hourly`)
- **Endpoint**: `api.open-meteo.com/v1/forecast`
- **Cadence**: Daily (all cities)
- **Time Window**: Next 7 Days (Hourly) = **168 rows per city per day**
- **Variables Retrieved**:
  - `temperature_2m` (°C at 2 meters)
  - `precipitation_mm` (mm/hour)
  - `wind_speed_10m` (km/h)
  - `wind_gusts_10m` (km/h)
  - `weather_code` (WMO Weather interpretation codes)

### 2. Air Quality (`raw.air_quality_hourly`)
- **Endpoint**: `air-quality-api.open-meteo.com/v1/air-quality`
- **Cadence**: Daily (all cities)
- **Time Window**: Next 5 Days (Hourly) = **120 rows per city per day**
- **Variables Retrieved**:
  - `european_aqi` (European Air Quality Index, 0–500 scale)
  - `pm2_5` (Particulate Matter < 2.5 µm in µg/m³)
  - `pm10` (Particulate Matter < 10 µm in µg/m³)
  - `nitrogen_dioxide` (NO₂ in µg/m³)
  - `o3` (Ozone in µg/m³)

### 3. River Discharge (`raw.flood_daily`)
- **Endpoint**: `flood-api.open-meteo.com/v1/flood`
- **Cadence**: Daily (river-enabled cities only — Paris, Amsterdam, Warsaw)
- **Time Window**: Next 7 Days (Daily) = **7 rows per city per day**
- **Variables Retrieved**:
  - `river_discharge_m3s` (River discharge in m³/s — nearest river within 5 km of coordinates)

### 4. Historical Weather — ERA5 Reanalysis (`raw.historical_weather_daily`)
- **Endpoint**: `archive-api.open-meteo.com/v1/archive`
- **Cadence**: Daily (all cities)
- **Time Window**: Rolling 7-day window (`today-12` to `today-6`) = **7 rows per city per day**
- **Note**: ERA5 has a ~5-day publication lag. The fetch window is offset to guarantee only confirmed, non-partial data is ingested.
- **Variables Retrieved**:
  - `temperature_2m_mean` (Daily mean temperature in °C)
  - `temperature_2m_max` (Daily maximum temperature in °C)
  - `temperature_2m_min` (Daily minimum temperature in °C)
  - `precipitation_sum_mm` (Total daily precipitation in mm)
  - `wind_speed_10m_max` (Maximum daily wind speed in km/h)

### 5. Climate Projections — CMIP6 (`raw.climate_projections_daily`)
- **Endpoint**: `climate-api.open-meteo.com/v1/climate`
- **Cadence**: Monthly (1st of month only — all cities)
- **Time Window**: Next 10 years (Daily) = **~3,650 rows per city per month**
- **Model**: `MRI_AGCM3_2_S` (high-resolution atmospheric model)
- **Variables Retrieved**:
  - `temperature_2m_max` (Projected daily maximum temperature in °C)
  - `temperature_2m_min` (Projected daily minimum temperature in °C)
  - `precipitation_sum_mm` (Projected total daily precipitation in mm)
  - `wind_speed_10m_max` (Projected maximum daily wind speed in km/h)

---

## Daily Volume Summary

| Source | Rows/city/run | Cities | Frequency | Daily Total |
|---|---|---|---|---|
| Weather Forecast | 168 | 10 | Daily | 1,680 |
| Air Quality | 120 | 10 | Daily | 1,200 |
| River Discharge | 7 | 3 | Daily | 21 |
| Historical (ERA5) | 7 | 10 | Daily | 70 |
| Climate (CMIP6) | ~3,650 | 10 | Monthly | ~36,500/mo |
| **Daily total** | | | | **~2,971** |

---

## Ingestion Metadata

Every row inserted into BigQuery is stamped with two metadata fields for traceability:

| Field | Type | Description |
|---|---|---|
| `ingestion_run_id` | `STRING` | UUID v4 unique to each pipeline run |
| `ingested_at_utc` | `TIMESTAMP` | UTC timestamp when the run started |

These fields enable deduplication in the staging layer and full audit trail of when each row was loaded.

## Table Auto-Creation

You do not need to manage BigQuery table schemas manually or via Terraform. The Python script (`loader.py`) uses `client.create_table(exists_ok=True)` to dynamically spin up all five raw tables on its very first run, saving you from writing extensive and verbose DDL files.
