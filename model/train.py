import os
import subprocess
import pandas as pd
import dagshub
import mlflow
import mlflow.sklearn
from sklearn.ensemble import RandomForestRegressor
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_squared_error, mean_absolute_error, r2_score

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
    
    # One-hot encode city_id so the model learns city-specific behavior
    # We include current_tipping_score as a core baseline feature
    feature_cols = ['current_tipping_score', 'temperature_2m_max', 'temperature_2m_min', 'precipitation_sum_mm', 'wind_speed_10m_max', 'european_aqi_max', 'river_discharge_m3s', 'city_id']
    target = 'future_tipping_score_3d'
    
    df_features = df[feature_cols].copy()
    X = pd.get_dummies(df_features, columns=['city_id'], drop_first=True)
    y = df[target]
    
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
    
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
        
        model = RandomForestRegressor(**params)
        model.fit(X_train, y_train)
        
        predictions = model.predict(X_test)
        
        # Metrics
        mse = mean_squared_error(y_test, predictions)
        mae = mean_absolute_error(y_test, predictions)
        r2 = r2_score(y_test, predictions)
        
        mlflow.log_metric("mse", mse)
        mlflow.log_metric("mae", mae)
        mlflow.log_metric("r2", r2)
        
        print(f"Model trained! MSE: {mse:.2f}, R2: {r2:.2f}")
        
        # Register Model to DagsHub MLflow Registry
        mlflow.sklearn.log_model(
            sk_model=model,
            artifact_path="random_forest_model",
            registered_model_name="ClimaSentinel_RiskForecaster"
        )
        print("Model successfully registered to MLflow!")

if __name__ == "__main__":
    train_model()
