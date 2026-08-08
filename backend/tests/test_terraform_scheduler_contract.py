"""Static contract for the production ingestion schedule."""

from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
TERRAFORM_MAIN_PATH = REPOSITORY_ROOT / "infra" / "terraform" / "main.tf"
TERRAFORM_VARIABLES_PATH = REPOSITORY_ROOT / "infra" / "terraform" / "variables.tf"


def test_ingestion_scheduler_runs_at_06_and_18_utc_without_replacement() -> None:
    terraform_main = TERRAFORM_MAIN_PATH.read_text(encoding="utf-8")
    terraform_variables = TERRAFORM_VARIABLES_PATH.read_text(encoding="utf-8")

    assert 'default     = "0 6,18 * * *"' in terraform_variables
    assert 'resource "google_cloud_scheduler_job" "ingest_daily"' in terraform_main
    assert 'name             = "clima-sentinel-ingest-daily"' in terraform_main
    assert "schedule         = var.ingest_schedule" in terraform_main
    assert 'time_zone        = "UTC"' in terraform_main
