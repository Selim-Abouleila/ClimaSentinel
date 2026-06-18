"""
Application settings — loaded from environment variables (12-Factor).
"""

from pydantic_settings import BaseSettings
from pydantic import ConfigDict
from functools import lru_cache


class Settings(BaseSettings):
    """
    All config comes from env vars.  Deployment platforms inject these
    per environment (dev / staging / production).
    """

    model_config = ConfigDict(env_file=".env", case_sensitive=True)

    # ── App ──────────────────────────────────────────────────────────────
    APP_NAME: str = "ClimaSentinel API"
    APP_VERSION: str = "0.1.0"
    ENVIRONMENT: str = "development"          # development | staging | production
    DEBUG: bool = False

    # ── Server ───────────────────────────────────────────────────────────
    HOST: str = "0.0.0.0"
    PORT: int = 8000


@lru_cache()
def get_settings() -> Settings:
    return Settings()
