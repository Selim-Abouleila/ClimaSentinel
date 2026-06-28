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
    
    # Drop rows where the future target or future forecast is null
    # Also handle missing river discharge (replace with 0)
    df['river_discharge_m3s'] = df['river_discharge_m3s'].fillna(0)
    df = df.dropna(subset=['current_tipping_score', 'future_tipping_score_3d', 'temp_forecast_plus_3d'])
    
    output_path = "model/data/training_snapshot.csv"
    os.makedirs("model/data", exist_ok=True)
    df.to_csv(output_path, index=False)
    print(f"Successfully exported {len(df)} rows to {output_path}")

if __name__ == "__main__":
    extract_data()
