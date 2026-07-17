import os
import subprocess
import pandas as pd
import dagshub
import mlflow
import mlflow.sklearn
import joblib
from mlflow.models import infer_signature
from sklearn.metrics import mean_squared_error, mean_absolute_error, r2_score

from backend.app.ml_pipeline import (
    FEATURE_SCHEMA_VERSION,
    FORECAST_HORIZONS,
    TARGET_COLUMNS,
    TARGET_COLUMNS_BY_HORIZON,
    build_model_pipeline,
    chronological_purged_split,
    output_slice_for_horizon,
    prepare_feature_frame,
)

def get_git_commit():
    return subprocess.check_output(['git', 'rev-parse', 'HEAD']).decode('ascii').strip()

def get_dvc_hash():
    # Read the DVC metadata file to get the hash of the dataset
    try:
        import yaml
        with open('model/data/training_snapshot.csv.dvc', 'r') as f:
            dvc_meta = yaml.safe_load(f)
            return dvc_meta['outs'][0]['md5']
    except Exception:
        return "unknown"


def train_model():
    print("Loading data snapshot...")
    df = pd.read_csv("model/data/training_snapshot.csv")
    
    # Sort chronologically to prevent future data leakage during train/test split
    df = df.sort_values(by=['date', 'city_id']).reset_index(drop=True)
    
    X = prepare_feature_frame(df)
    y = df.loc[:, list(TARGET_COLUMNS)].copy()
    
    # Split on complete dates and purge the three days before the test window
    # so no training target date overlaps the held-out period.
    X_train, X_test, y_train, y_test, test_start = chronological_purged_split(
        X,
        y,
        df["date"],
    )
    
    # Clean up any accidental newlines from GitHub Secrets
    dagshub_username = os.environ.get("DAGSHUB_USERNAME", "Selim-Abouleila").strip()
    dagshub_token = os.environ.get("DAGSHUB_USER_TOKEN", "").strip()
    
    # Update env vars so dagshub.init picks up the clean token/username internally
    if dagshub_token:
        os.environ["DAGSHUB_USER_TOKEN"] = dagshub_token
    os.environ["DAGSHUB_USERNAME"] = dagshub_username

    # Setup MLflow via DagsHub client
    dagshub.init(
        repo_owner=dagshub_username,
        repo_name="ClimaSentinel",
        mlflow=True
    )
    mlflow.set_experiment("ClimaSentinel_Forecasting")
    
    with mlflow.start_run():
        print("Training Random Forest Regressor...")
        params = {
            "n_estimators": 100,
            "max_depth": 10,
            "random_state": 42
        }
        
        # Log requirements
        mlflow.log_params(params)
        mlflow.log_param("git_commit", get_git_commit())
        mlflow.log_param("dvc_data_hash", get_dvc_hash())
        mlflow.log_param("feature_schema_version", FEATURE_SCHEMA_VERSION)
        mlflow.log_param("forecast_horizons", ",".join(map(str, FORECAST_HORIZONS)))
        mlflow.log_param("test_start_date", test_start.date().isoformat())
        mlflow.log_param("purge_gap_days", max(FORECAST_HORIZONS))
        
        model = build_model_pipeline(params)
        model.fit(X_train, y_train)
        
        predictions = model.predict(X_test)
        
        # Metrics
        mse = mean_squared_error(y_test, predictions)
        mae = mean_absolute_error(y_test, predictions)
        r2_avg = r2_score(y_test, predictions)  # Uniform average across 15 targets
        
        mlflow.log_metric("mse", mse)
        mlflow.log_metric("mae", mae)
        mlflow.log_metric("r2", r2_avg)

        print(f"Model trained! MSE: {mse:.2f}, R2 Average: {r2_avg:.2f}")
        for horizon in FORECAST_HORIZONS:
            target_columns = TARGET_COLUMNS_BY_HORIZON[horizon]
            horizon_slice = output_slice_for_horizon(horizon)
            horizon_targets = y_test.loc[:, list(target_columns)]
            horizon_predictions = predictions[:, horizon_slice]
            horizon_mae = mean_absolute_error(
                horizon_targets,
                horizon_predictions,
            )
            horizon_r2 = r2_score(
                horizon_targets,
                horizon_predictions,
            )
            horizon_r2_raw = r2_score(
                horizon_targets,
                horizon_predictions,
                multioutput="raw_values",
            )
            horizon_mae_raw = mean_absolute_error(
                horizon_targets,
                horizon_predictions,
                multioutput="raw_values",
            )
            mlflow.log_metric(f"mae_d{horizon}", horizon_mae)
            mlflow.log_metric(f"r2_d{horizon}", horizon_r2)
            print(
                f"  Day +{horizon}: MAE {horizon_mae:.2f}, "
                f"R2 {horizon_r2:.2f}"
            )
            for target, target_r2, target_mae in zip(
                target_columns,
                horizon_r2_raw,
                horizon_mae_raw,
            ):
                score_name = target.removeprefix("future_").removesuffix(
                    f"_{horizon}d"
                )
                mlflow.log_metric(
                    f"r2_{score_name}_d{horizon}",
                    target_r2,
                )
                mlflow.log_metric(
                    f"mae_{score_name}_d{horizon}",
                    target_mae,
                )
                print(
                    f"    {target}: R2 {target_r2:.2f}, "
                    f"MAE {target_mae:.2f}"
                )

        input_example = X_train.head(min(5, len(X_train))).copy()
        output_example = model.predict(input_example)
        signature = infer_signature(input_example, output_example)
        
        # Register Model to DagsHub MLflow Registry
        model_info = mlflow.sklearn.log_model(
            sk_model=model,
            artifact_path="random_forest_model",
            registered_model_name="ClimaSentinel_RiskForecaster",
            signature=signature,
            input_example=input_example,
            serialization_format=mlflow.sklearn.SERIALIZATION_FORMAT_CLOUDPICKLE,
        )
        print("Model successfully registered to MLflow!")
        registered_version = model_info.registered_model_version
        if registered_version is None:
            raise RuntimeError("MLflow did not return a concrete registered model version")
        registered_version = str(registered_version)
        print(f"REGISTERED_MODEL_VERSION={registered_version}")
        github_output = os.environ.get("GITHUB_OUTPUT")
        if github_output:
            with open(github_output, "a", encoding="utf-8") as output_file:
                output_file.write(f"model_version={registered_version}\n")
        
        # Save a robust local model artifact for the FastAPI backend inference
        os.makedirs("backend/app", exist_ok=True)
        joblib.dump(model, "backend/app/risk_forecaster.pkl")
        print("Model successfully saved to backend/app/risk_forecaster.pkl!")

if __name__ == "__main__":
    train_model()
