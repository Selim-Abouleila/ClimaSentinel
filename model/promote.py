import os
import sys
import logging
import mlflow
from mlflow.tracking import MlflowClient

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

SCORE_NAMES = ("heat_score", "wind_score", "rain_score", "air_score", "river_score")

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
    model_alias = (
        os.environ.get("MLFLOW_MODEL_ALIAS", "champion").strip()
        or "champion"
    )
    configured_version = os.environ.get("MLFLOW_MODEL_VERSION", "").strip()
    
    try:
        # 2. Evaluate the exact version produced by the current training run.
        # Manual invocations retain the existing latest-candidate fallback.
        if configured_version:
            if not configured_version.isdigit() or int(configured_version) <= 0:
                logging.error("MLFLOW_MODEL_VERSION must be a positive integer.")
                sys.exit(1)
            candidate_version = client.get_model_version(
                model_name,
                str(int(configured_version)),
            )
        else:
            versions = client.search_model_versions(f"name='{model_name}'")
            if not versions:
                logging.error(f"No versions found for model '{model_name}'.")
                sys.exit(1)
            candidate_version = sorted(
                versions,
                key=lambda version: int(version.version),
            )[-1]

        run_id = candidate_version.run_id
        logging.info(
            "Evaluating Model '%s' (Version %s, Run ID: %s)",
            model_name,
            candidate_version.version,
            run_id,
        )

        # 3. Fetch the metrics for this run
        run = client.get_run(run_id)
        metrics = run.data.metrics
        
        if run.data.params.get("feature_schema_version") != "2":
            logging.error("Candidate does not use multi-horizon feature schema 2.")
            sys.exit(1)
        if run.data.params.get("forecast_horizons") != "1,2,3":
            logging.error("Candidate does not declare Day +1/+2/+3 horizons.")
            sys.exit(1)

        # 4. Evaluate against Quality Gate Thresholds
        R2_THRESHOLD = 0.35
        MAE_THRESHOLD = 7.0
        
        horizon_metrics = {}
        component_metrics = {}
        for horizon in (1, 2, 3):
            r2 = metrics.get(f"r2_d{horizon}")
            mae = metrics.get(f"mae_d{horizon}")
            if r2 is None or mae is None:
                logging.error(
                    "Required Day +%s metrics are missing from run %s.",
                    horizon,
                    run_id,
                )
                sys.exit(1)
            horizon_metrics[horizon] = (r2, mae)
            logging.info(
                "Day +%s metrics -> R2: %.4f, MAE: %.4f",
                horizon,
                r2,
                mae,
            )
            for score_name in SCORE_NAMES:
                component_r2 = metrics.get(f"r2_{score_name}_d{horizon}")
                component_mae = metrics.get(f"mae_{score_name}_d{horizon}")
                if component_r2 is None or component_mae is None:
                    logging.error(
                        "Required Day +%s %s metrics are missing from run %s.",
                        horizon,
                        score_name,
                        run_id,
                    )
                    sys.exit(1)
                component_metrics[(horizon, score_name)] = (
                    component_r2,
                    component_mae,
                )
                logging.info(
                    "Day +%s %s -> R2: %.4f, MAE: %.4f",
                    horizon,
                    score_name,
                    component_r2,
                    component_mae,
                )

        if all(
            r2 >= R2_THRESHOLD and mae <= MAE_THRESHOLD
            for r2, mae in (
                *horizon_metrics.values(),
                *component_metrics.values(),
            )
        ):
            logging.info("✅ Quality gates passed.")
            client.transition_model_version_stage(
                name=model_name,
                version=candidate_version.version,
                stage="Production",
                archive_existing_versions=True
            )
            client.set_registered_model_alias(
                model_name,
                model_alias,
                candidate_version.version,
            )
            logging.info(
                "Assigned alias '%s' to model version %s.",
                model_alias,
                candidate_version.version,
            )
            logging.info("Model successfully promoted to Production.")
        else:
            logging.error(
                "❌ Quality Gates Failed! Every horizon and component must satisfy "
                f"R2 >= {R2_THRESHOLD} and MAE <= {MAE_THRESHOLD}"
            )
            sys.exit(1)

    except Exception as e:
        logging.error(f"An error occurred during promotion evaluation: {e}")
        sys.exit(1)

if __name__ == "__main__":
    promote_model()
