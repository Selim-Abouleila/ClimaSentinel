import os
import pandas as pd
from google.cloud import bigquery

from backend.app.ml_pipeline import FEATURE_COLUMNS, TARGET_COLUMNS

# We expect GCP_PROJECT_ID to be injected by Github Actions
project_id = os.getenv("GCP_PROJECT_ID", "climasentinel")
dataset = os.getenv("BQ_DATASET", "mart")
staging_dataset = "stg"

def extract_data():
    client = bigquery.Client()

    feature_projection = ",\n                ".join(
        f"f.`{column}`" for column in FEATURE_COLUMNS
    )
    target_projection = ",\n                ".join(
        f"s{horizon}.`{target.removeprefix('future_').removesuffix(f'_{horizon}d')}` "
        f"AS `{target}`"
        for horizon in (1, 2, 3)
        for target in TARGET_COLUMNS
        if target.endswith(f"_{horizon}d")
    )

    # Join score history by exact target date so Day +1/+2/+3 labels are
    # available even before the expanded dbt mart is materialized.
    query = f"""
        SELECT
                f.date,
                {feature_projection},
                {target_projection}
        FROM `{project_id}.{dataset}.mart_ml_feature_store` f
        LEFT JOIN `{project_id}.{dataset}.mart_city_score_history` s1
          ON s1.city_id = f.city_id
         AND s1.date = DATE_ADD(f.date, INTERVAL 1 DAY)
        LEFT JOIN `{project_id}.{dataset}.mart_city_score_history` s2
          ON s2.city_id = f.city_id
         AND s2.date = DATE_ADD(f.date, INTERVAL 2 DAY)
        LEFT JOIN `{project_id}.{dataset}.mart_city_score_history` s3
          ON s3.city_id = f.city_id
         AND s3.date = DATE_ADD(f.date, INTERVAL 3 DAY)
        ORDER BY f.city_id, f.date
    """
    
    print("Extracting data from BigQuery Feature Store...")
    df = client.query(query).to_dataframe()
    
    # 1. River Discharge: Fill with 0 (Valid for cities without rivers)
    river_cols = ['river_discharge_m3s', 'river_forecast_plus_1d', 'river_forecast_plus_2d', 'river_forecast_plus_3d', 'river_forecast_plus_4d']
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

    # Drop rows without the complete horizon-specific target matrix.
    df = df.dropna(
        subset=["current_tipping_score", "temp_forecast_plus_3d", *TARGET_COLUMNS]
    )
    
    output_path = "model/data/training_snapshot.csv"
    os.makedirs("model/data", exist_ok=True)
    df.to_csv(output_path, index=False)
    print(f"Successfully exported {len(df)} rows to {output_path}")

if __name__ == "__main__":
    extract_data()
