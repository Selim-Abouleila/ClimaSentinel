import os
import pandas as pd
from google.cloud import bigquery

# We expect GCP_PROJECT_ID to be injected by Github Actions
project_id = os.getenv("GCP_PROJECT_ID", "climasentinel")
dataset = os.getenv("BQ_DATASET", "mart")
staging_dataset = "stg"

def extract_data():
    client = bigquery.Client()
    
    # Extract weather features (from today) and join with the tipping score from 7 days in the future
    query = f"""
        SELECT 
            f.city_id,
            f.date,
            f.temperature_2m_max,
            f.temperature_2m_min,
            f.precipitation_sum_mm,
            f.wind_speed_10m_max,
            f.european_aqi_max,
            f.river_discharge_m3s,
            LEAD(s.global_tipping_score, 7) OVER (PARTITION BY f.city_id ORDER BY f.date) as future_tipping_score_7d
        FROM `{project_id}.{staging_dataset}.stg_city_signal_input` f
        LEFT JOIN `{project_id}.{dataset}.mart_city_score_history` s
            ON f.city_id = s.city_id AND f.date = s.date
        ORDER BY f.city_id, f.date
    """
    
    print("Extracting data from BigQuery...")
    df = client.query(query).to_dataframe()
    
    # Drop rows where the future score is null (we can't train on what we don't know yet)
    # Also handle missing river discharge (replace with 0)
    df['river_discharge_m3s'] = df['river_discharge_m3s'].fillna(0)
    df = df.dropna(subset=['future_tipping_score_7d'])
    
    output_path = "model/data/training_snapshot.csv"
    os.makedirs("model/data", exist_ok=True)
    df.to_csv(output_path, index=False)
    print(f"Successfully exported {len(df)} rows to {output_path}")

if __name__ == "__main__":
    extract_data()
