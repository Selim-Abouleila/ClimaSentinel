import os
import sys
import logging
import mlflow
from mlflow.tracking import MlflowClient

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

def promote_model():
    # 1. Authenticate with DagsHub MLflow Registry
    dagshub_username = os.environ.get("DAGSHUB_USERNAME", "Selim-Abouleila").strip()
    dagshub_token = os.environ.get("DAGSHUB_USER_TOKEN", "").strip()
    
    if not dagshub_token:
        logging.error("Missing DAGSHUB_USER_TOKEN environment variable.")
        sys.exit(1)

    try:
        import dagshub
        dagshub.init(repo_owner=dagshub_username, repo_name="ClimaSentinel", mlflow=True)
    except Exception as e:
        logging.error(f"Failed to initialize DagsHub: {e}")
        sys.exit(1)

    client = MlflowClient()
    model_name = "ClimaSentinel_RiskForecaster"
    
    try:
        # 2. Fetch the latest version of the model
        versions = client.search_model_versions(f"name='{model_name}'")
        if not versions:
            logging.error(f"No versions found for model '{model_name}'.")
            sys.exit(1)
            
        latest_version = sorted(versions, key=lambda v: int(v.version))[-1]
        run_id = latest_version.run_id
        logging.info(f"Evaluating Model '{model_name}' (Version {latest_version.version}, Run ID: {run_id})")

        # 3. Fetch the metrics for this run
        run = client.get_run(run_id)
        metrics = run.data.metrics
        
        r2 = metrics.get("r2")
        mae = metrics.get("mae")
        
        if r2 is None or mae is None:
            logging.error(f"Required metrics (r2, mae) are missing from the run {run_id}. Found: {list(metrics.keys())}")
            sys.exit(1)
            
        logging.info(f"Fetched Metrics -> R2: {r2:.4f}, MAE: {mae:.4f}")

        # 4. Evaluate against Quality Gate Thresholds
        R2_THRESHOLD = 0.45
        MAE_THRESHOLD = 7.0
        
        if r2 >= R2_THRESHOLD and mae <= MAE_THRESHOLD:
            logging.info("✅ Quality Gates Passed! Promoting model to 'Production'.")
            client.transition_model_version_stage(
                name=model_name,
                version=latest_version.version,
                stage="Production",
                archive_existing_versions=True
            )
            logging.info("Model successfully promoted to Production.")
        else:
            logging.error(f"❌ Quality Gates Failed! Expected R2 >= {R2_THRESHOLD} and MAE <= {MAE_THRESHOLD}")
            sys.exit(1)

    except Exception as e:
        logging.error(f"An error occurred during promotion evaluation: {e}")
        sys.exit(1)

if __name__ == "__main__":
    promote_model()
