import json
import logging
from google.cloud import bigquery
from google.oauth2 import service_account

from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

def get_bq_client() -> bigquery.Client:
    """
    Initializes and returns a BigQuery client.
    Uses GCP_CREDENTIALS_JSON if provided (production/CI),
    otherwise falls back to Application Default Credentials (local dev).
    """
    if settings.GCP_CREDENTIALS_JSON:
        try:
            # Load credentials from the JSON string
            creds_info = json.loads(settings.GCP_CREDENTIALS_JSON)
            credentials = service_account.Credentials.from_service_account_info(creds_info)
            return bigquery.Client(project=settings.GCP_PROJECT_ID, credentials=credentials)
        except Exception as e:
            logger.error(f"Failed to load BigQuery credentials from JSON: {e}")
            raise
    else:
        # Fallback to local ADC (e.g. gcloud auth application-default login)
        return bigquery.Client(project=settings.GCP_PROJECT_ID)
