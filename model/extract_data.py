import os
import pandas as pd
from google.cloud import bigquery

# We expect GCP_PROJECT_ID to be injected by Github Actions
project_id = os.getenv("GCP_PROJECT_ID", "climasentinel")
dataset = os.getenv("BQ_DATASET", "mart")
staging_dataset = "stg"

def extract_data():
    client = bigquery.Client()
    
    # Pull pre-computed feature vectors directly from our dbt materialized Feature Store
    query = f"""
        SELECT *
        FROM `{project_id}.{dataset}.mart_ml_feature_store`
        ORDER BY city_id, date
    """
    
    print("Extracting data from BigQuery Feature Store...")
    df = client.query(query).to_dataframe()
    
    # 1. River Discharge: Fill with 0 (Valid for cities without rivers)
    river_cols = ['river_discharge_m3s', 'river_forecast_plus_1d', 'river_forecast_plus_2d', 'river_forecast_plus_3d']
    df[river_cols] = df[river_cols].fillna(0)
    
    # 2. Wind Gusts: Fallback to average wind speed if gust sensor data is missing
    df['wind_gusts_10m_max'] = df['wind_gusts_10m_max'].fillna(df['wind_speed_10m_max'])
    df['wind_gusts_forecast_plus_1d'] = df['wind_gusts_forecast_plus_1d'].fillna(df['wind_forecast_plus_1d'])
    df['wind_gusts_forecast_plus_2d'] = df['wind_gusts_forecast_plus_2d'].fillna(df['wind_forecast_plus_2d'])
    df['wind_gusts_forecast_plus_3d'] = df['wind_gusts_forecast_plus_3d'].fillna(df['wind_forecast_plus_3d'])
    
    # 3. AQI: Scientifically rigorous City-Specific Forward-Fill (and Backward-Fill for first days)
    aqi_cols = ['european_aqi_max', 'aqi_forecast_plus_1d', 'aqi_forecast_plus_2d', 'aqi_forecast_plus_3d']
    df[aqi_cols] = df.groupby('city_id')[aqi_cols].ffill().bfill()
    # If a city has absolutely NO AQI data, fallback to the global median to prevent crashes
    df[aqi_cols] = df[aqi_cols].fillna(df[aqi_cols].median())

    # Drop rows where the future target is null (the final 3 days of the timeline)
    df = df.dropna(subset=['current_tipping_score', 'future_tipping_score_3d', 'future_heat_score_3d', 'temp_forecast_plus_3d'])
    
    output_path = "model/data/training_snapshot.csv"
    os.makedirs("model/data", exist_ok=True)
    df.to_csv(output_path, index=False)
    print(f"Successfully exported {len(df)} rows to {output_path}")

if __name__ == "__main__":
    extract_data()
