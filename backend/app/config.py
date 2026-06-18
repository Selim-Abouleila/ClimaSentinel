"""
Application settings — loaded from environment variables (12-Factor).
"""

from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    """
    All config comes from env vars.  Railway / GitHub Actions inject these
    per environment (dev / staging / production).
    """

    # ── App ──────────────────────────────────────────────────────────────
    APP_NAME: str = "ClimaSentinel API"
    APP_VERSION: str = "0.1.0"
    ENVIRONMENT: str = "development"          # development | staging | production
    DEBUG: bool = False

    # ── MLflow / DagsHub ─────────────────────────────────────────────────
    MLFLOW_TRACKING_URI: str = ""             # e.g. https://dagshub.com/<user>/<repo>.mlflow
    MLFLOW_MODEL_NAME: str = "clima-sentinel" # registered model name
    MLFLOW_MODEL_STAGE: str = "Production"    # Production | Staging

    # ── Google Cloud / BigQuery ──────────────────────────────────────────
    GCP_PROJECT_ID: str = ""
    GCP_CREDENTIALS_JSON: str = ""            # service-account key JSON (as string)
    BQ_DATASET: str = "mart"                  # dataset to read features from

    # ── Server ───────────────────────────────────────────────────────────
    HOST: str = "0.0.0.0"
    PORT: int = 8000

    class Config:
        env_file = ".env"
        case_sensitive = True


@lru_cache()
def get_settings() -> Settings:
    return Settings()
