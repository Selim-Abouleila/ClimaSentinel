import os
import subprocess
import pandas as pd
import dagshub
import mlflow
import mlflow.sklearn
import joblib
from mlflow.models import infer_signature
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_squared_error, mean_absolute_error, r2_score

from backend.app.ml_pipeline import (
    FEATURE_SCHEMA_VERSION,
    TARGET_COLUMNS,
    build_model_pipeline,
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
    
    # Time-based split (no shuffle) to strictly evaluate future generalization
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, shuffle=False)
    
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
        
        model = build_model_pipeline(params)
        model.fit(X_train, y_train)
        
        predictions = model.predict(X_test)
        
        # Metrics
        mse = mean_squared_error(y_test, predictions)
        mae = mean_absolute_error(y_test, predictions)
        r2_avg = r2_score(y_test, predictions) # Uniform average across all 5 targets
        
        # Calculate individual R2 scores for each sub-score
        r2_raw = r2_score(y_test, predictions, multioutput='raw_values')
        
        mlflow.log_metric("mse", mse)
        mlflow.log_metric("mae", mae)
        mlflow.log_metric("r2", r2_avg)
        
        for name, r2_val in zip(TARGET_COLUMNS, r2_raw):
            mlflow.log_metric(f"r2_{name.replace('future_', '').replace('_3d', '')}", r2_val)
        
        print(f"Model trained! MSE: {mse:.2f}, R2 Average: {r2_avg:.2f}")
        for name, r2_val in zip(TARGET_COLUMNS, r2_raw):
            print(f"  R2 {name}: {r2_val:.2f}")

        input_example = X_train.head(min(5, len(X_train))).copy()
        output_example = model.predict(input_example)
        signature = infer_signature(input_example, output_example)
        
        # Register Model to DagsHub MLflow Registry
        mlflow.sklearn.log_model(
            sk_model=model,
            artifact_path="random_forest_model",
            registered_model_name="ClimaSentinel_RiskForecaster",
            signature=signature,
            input_example=input_example,
            serialization_format=mlflow.sklearn.SERIALIZATION_FORMAT_CLOUDPICKLE,
        )
        print("Model successfully registered to MLflow!")
        
        # Save a robust local model artifact for the FastAPI backend inference
        os.makedirs("backend/app", exist_ok=True)
        joblib.dump(model, "backend/app/risk_forecaster.pkl")
        print("Model successfully saved to backend/app/risk_forecaster.pkl!")

if __name__ == "__main__":
    train_model()
