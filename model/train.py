import os
import subprocess
from pathlib import Path

import numpy as np
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
    MAX_LABEL_LOOKAHEAD_DAYS,
    REGISTERED_MODEL_NAME,
    TARGET_SCHEMA_VERSION,
    TARGET_SCORE_NAMES,
    TRAINING_DATA_CONTRACT,
    TARGET_COLUMNS,
    TARGET_COLUMNS_BY_HORIZON,
    build_model_pipeline,
    chronological_purged_split,
    output_slice_for_horizon,
    prepare_feature_frame,
)
from model.extract_data import (
    CANONICAL_VINTAGE_RULE,
    LABEL_SOURCE,
    SUPPORTED_TARGET_COMPONENTS,
    UNSUPPORTED_TARGET_COMPONENTS,
    validate_training_frame,
)


TRAINING_SNAPSHOT_PATH = Path("model/data/training_snapshot.csv")

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


def _single_contract_value(df: pd.DataFrame, column: str, expected: str) -> str:
    values = set(df[column].astype(str).unique())
    if values != {expected}:
        raise ValueError(
            f"Training snapshot contract field {column!r} must equal "
            f"{expected!r}; found {sorted(values)!r}"
        )
    return expected


def train_model():
    print("Loading data snapshot...")
    df = validate_training_frame(pd.read_csv(TRAINING_SNAPSHOT_PATH))
    
    # Sort chronologically to prevent future data leakage during train/test split
    df = df.sort_values(
        by=["forecast_origin_date", "city_id", "ingestion_run_id"]
    ).reset_index(drop=True)
    
    X = prepare_feature_frame(df)
    y = df.loc[:, list(TARGET_COLUMNS)].apply(pd.to_numeric, errors="raise")
    if not np.isfinite(y.to_numpy(dtype=float)).all():
        raise ValueError("Training targets must be complete and finite")
    
    # Day +3 Heat needs the following realized day to finalize its label. Purge
    # the complete four-day dependency window before the held-out period.
    X_train, X_test, y_train, y_test, test_start = chronological_purged_split(
        X,
        y,
        df["forecast_origin_date"],
        purge_days=MAX_LABEL_LOOKAHEAD_DAYS,
    )

    parsed_dates = pd.to_datetime(df["forecast_origin_date"], errors="raise")
    # chronological_purged_split resets returned indexes, so derive audit date
    # counts from the contract boundary rather than those reset indexes.
    purge_boundary = test_start - pd.Timedelta(
        MAX_LABEL_LOOKAHEAD_DAYS,
        unit="D",
    )
    source_train_dates = parsed_dates[parsed_dates < purge_boundary]
    source_test_dates = parsed_dates[parsed_dates >= test_start]
    
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
        contract_params = {
            "git_commit": get_git_commit(),
            "dvc_data_hash": get_dvc_hash(),
            "feature_schema_version": FEATURE_SCHEMA_VERSION,
            "target_schema_version": TARGET_SCHEMA_VERSION,
            "training_data_contract": TRAINING_DATA_CONTRACT,
            "registered_model_name": REGISTERED_MODEL_NAME,
            "forecast_horizons": ",".join(map(str, FORECAST_HORIZONS)),
            "target_score_names": ",".join(TARGET_SCORE_NAMES),
            "target_columns": ",".join(TARGET_COLUMNS),
            "output_count": str(len(TARGET_COLUMNS)),
            "label_source": _single_contract_value(
                df, "label_source", LABEL_SOURCE
            ),
            "supported_target_components": _single_contract_value(
                df,
                "supported_target_components",
                SUPPORTED_TARGET_COMPONENTS,
            ),
            "unsupported_target_components": _single_contract_value(
                df,
                "unsupported_target_components",
                UNSUPPORTED_TARGET_COMPONENTS,
            ),
            "canonical_vintage_rule": _single_contract_value(
                df, "canonical_vintage_rule", CANONICAL_VINTAGE_RULE
            ),
            "training_grain": "city_id,forecast_origin_date",
            "test_start_date": test_start.date().isoformat(),
            "purge_gap_days": str(MAX_LABEL_LOOKAHEAD_DAYS),
            "row_count": str(len(df)),
            "distinct_origin_dates": str(parsed_dates.nunique()),
            "train_rows": str(len(X_train)),
            "test_rows": str(len(X_test)),
            "train_distinct_origin_dates": str(source_train_dates.nunique()),
            "test_distinct_origin_dates": str(source_test_dates.nunique()),
            "first_origin_date": parsed_dates.min().date().isoformat(),
            "last_origin_date": parsed_dates.max().date().isoformat(),
        }
        mlflow.log_params(contract_params)
        
        model = build_model_pipeline(params)
        model.fit(X_train, y_train)
        
        predictions = model.predict(X_test)
        
        # Metrics
        mse = mean_squared_error(y_test, predictions)
        mae = mean_absolute_error(y_test, predictions)
        r2_avg = r2_score(y_test, predictions)  # Uniform average across six targets
        
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
                target_values = horizon_targets[target].to_numpy(dtype=float)
                mlflow.log_metric(
                    f"test_count_{score_name}_d{horizon}",
                    float(len(target_values)),
                )
                mlflow.log_metric(
                    f"test_std_{score_name}_d{horizon}",
                    float(np.std(target_values, ddof=0)),
                )
                mlflow.log_metric(
                    f"test_nonzero_count_{score_name}_d{horizon}",
                    float(np.count_nonzero(target_values)),
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
            name="random_forest_model",
            registered_model_name=REGISTERED_MODEL_NAME,
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
