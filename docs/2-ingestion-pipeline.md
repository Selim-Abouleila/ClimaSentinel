# 2. Ingestion Pipeline

The ClimaSentinel ingestion pipeline is a serverless, automated data pipeline running entirely on Google Cloud Platform. It scales to zero when idle and automatically fetches daily weather and air quality data for a configurable set of cities directly into BigQuery.

## Architecture

The ingestion process relies on three core Google Cloud services, all provisioned via Terraform:
1. **Cloud Scheduler**: Acts as a cron job, firing an HTTP request to the Cloud Run job once a day at `06:00 UTC` (`0 6 * * *`).
2. **Cloud Run Job**: Executes the Python runner which contains the application logic to pull from APIs and transform the results.
3. **BigQuery**: Provides the data warehouse where processed, raw climate data is appended into time-partitioned tables.

Additionally, **Artifact Registry** is used to store the Docker container image built via **Cloud Build**.

## Configuration: The City List

The ingestion script iterates over 10 major European cities configured in `config/cities.csv`. To add or remove cities, simply update the CSV and push.

| City | Country | Latitude | Longitude |
|---|---|---|---|
| Paris | FR | 48.853 | 2.348 |
| London | GB | 51.508 | -0.125 |
| Madrid | ES | 40.416 | -3.702 |
| Berlin | DE | 52.524 | 13.410 |
| Rome | IT | 41.891 | 12.511 |
| Amsterdam | NL | 52.374 | 4.889 |
| Athens | GR | 37.983 | 23.727 |
| Warsaw | PL | 52.229 | 21.011 |
| Lisbon | PT | 38.716 | -9.133 |
| Stockholm | SE | 59.329 | 18.068 |

---

## APIs & Data Retrieved

The Cloud Run job simultaneously fetches data from two Open-Meteo endpoints for each city, formats it as JSON, and streams it into the `raw` BigQuery dataset. Because tables are time-partitioned, no data is overwritten — historical forecasts are accumulated continuously over time allowing for forecast deviation monitoring.

### 1. Weather Forecast (`raw.weather_forecast_hourly`)
- **Endpoint**: `api.open-meteo.com/v1/forecast`
- **Time Window**: Next 7 Days (Hourly) = **168 rows per city per day**.
- **Variables Retrieved**:
  - `temperature_2m` (°C at 2 meters)
  - `precipitation_mm` (mm/hour)
  - `wind_speed_10m` (km/h)
  - `wind_gusts_10m` (km/h)
  - `weather_code` (WMO Weather interpretation codes)

### 2. Air Quality (`raw.air_quality_hourly`)
- **Endpoint**: `air-quality-api.open-meteo.com/v1/air-quality`
- **Time Window**: Next 5 Days (Hourly) = **120 rows per city per day**.
- **Variables Retrieved**:
  - `european_aqi` (0-500 scale)
  - `pm2_5` (Particulate Matter < 2.5 µm in µg/m³)
  - `pm10` (Particulate Matter < 10 µm in µg/m³)
  - `nitrogen_dioxide` (Nitrogen Dioxide in µg/m³)
  - `o3` (Ozone in µg/m³)

## Table Auto-Creation

You do not need to manage BigQuery table schemas manually or via Terraform. The Python script (`loader.py`) uses `client.create_table(exists_ok=True)` to dynamically spin up the `weather_forecast_hourly` and `air_quality_hourly` tables on its very first run, saving you from writing extensive and verbose DDL files.
