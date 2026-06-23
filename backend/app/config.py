"""
Application settings — loaded from environment variables (12-Factor).
"""

from pydantic_settings import BaseSettings
from functools import lru_cache
from typing import Optional


class Settings(BaseSettings):
    """
    All config comes from env vars. Defaults are for local development.
    """
    APP_NAME: str = "ClimaSentinel Backend"
    APP_VERSION: str = "1.0.0"
    ENVIRONMENT: str = "development"
    
    # GCP / BigQuery
    GCP_PROJECT_ID: str = "clima-sentinel"
    GCP_CREDENTIALS_JSON: Optional[str] = None
    BQ_DATASET: str = "mart"
    BQ_LOCATION: str = "europe-west9" 
    model_config = {"env_file": ".env"}


@lru_cache()
def get_settings():
    return Settings()
