# =============================================================================
# ClimaSentinel — Makefile
# =============================================================================
# Usage:
#   make bootstrap   → Create GCS Terraform state bucket & init backend
#   make build       → Build & push the ingest Docker image to Artifact Registry
#   make deploy      → Build image + terraform apply + dbt run (full pipeline)
#   make plan        → Terraform plan only (dry run, no build)
#   make destroy     → Terraform destroy (tear down all resources)
#   make dbt-run     → Run all dbt models (stg + mart)
#   make dbt-stg     → Run staging models only
#   make dbt-test    → Run dbt schema tests
#   make help        → Show this help message
# =============================================================================

.PHONY: bootstrap build deploy plan destroy dbt-run dbt-stg dbt-test help

TF_DIR  := infra/terraform
DBT_DIR := transform

# Load .env so PROJECT_ID and REGION are available
ifneq (,$(wildcard .env))
  include .env
  export
endif

GCP_PROJECT_ID ?= $(error GCP_PROJECT_ID is not set — copy .env.example to .env and fill it in)
GCP_REGION     ?= europe-west9
IMAGE_URI       = $(GCP_REGION)-docker.pkg.dev/$(GCP_PROJECT_ID)/clima-sentinel/ingest:latest

## Initialise GCS state bucket and Terraform backend
bootstrap:
	@chmod +x infra/bootstrap.sh
	@bash infra/bootstrap.sh

## Build & push the ingest Docker image via Cloud Build (no local Docker auth needed)
build:
	@echo "Submitting build to Cloud Build: $(IMAGE_URI)"
	gcloud builds submit \
		--config cloudbuild.yaml \
		--substitutions _IMAGE=$(IMAGE_URI) \
		--region $(GCP_REGION) \
		--project $(GCP_PROJECT_ID) \
		.
	@echo "Image built and pushed successfully: $(IMAGE_URI)"

## Full deploy: build image → terraform apply → dbt run (creates stg views)
deploy: build
	@terraform -chdir=$(TF_DIR) plan -out=tfplan \
		-var="project_id=$(GCP_PROJECT_ID)" \
		-var="region=$(GCP_REGION)" \
		-var="ingest_image=$(IMAGE_URI)"
	@terraform -chdir=$(TF_DIR) apply tfplan
	@echo ""
	@echo "── Installing dbt (if needed) ──────────────────────────────────"
	@pip install -q -r $(DBT_DIR)/requirements.txt
	@echo "── Seeding static data (CSV to BigQuery) ───────────────────────"
	@dbt seed --project-dir $(DBT_DIR) --profiles-dir $(DBT_DIR)
	@echo "── Running dbt models (staging views) ──────────────────────────"
	@dbt run --project-dir $(DBT_DIR) --profiles-dir $(DBT_DIR)
	@echo ""
	@echo "── Running dbt tests ───────────────────────────────────────────"
	@dbt test --project-dir $(DBT_DIR) --profiles-dir $(DBT_DIR)

## Dry run — show what Terraform would change without applying (no build)
plan:
	@terraform -chdir=$(TF_DIR) plan \
		-var="project_id=$(GCP_PROJECT_ID)" \
		-var="region=$(GCP_REGION)" \
		-var="ingest_image=$(IMAGE_URI)"

## Tear down all Terraform-managed GCP resources
destroy:
	@terraform -chdir=$(TF_DIR) destroy \
		-var="project_id=$(GCP_PROJECT_ID)" \
		-var="region=$(GCP_REGION)" \
		-var="ingest_image=$(IMAGE_URI)"

## Run all dbt models (stg + mart)
dbt-run:
	@dbt run --project-dir $(DBT_DIR) --profiles-dir $(DBT_DIR)

## Run staging models only
dbt-stg:
	@dbt run --project-dir $(DBT_DIR) --profiles-dir $(DBT_DIR) --select stg

## Run dbt schema tests
dbt-test:
	@dbt test --project-dir $(DBT_DIR) --profiles-dir $(DBT_DIR)

## Show available commands
help:
	@echo ""
	@echo "  ClimaSentinel — Available commands"
	@echo "  ─────────────────────────────────────────"
	@echo "  make bootstrap   Init GCS state bucket & Terraform backend"
	@echo "  make build       Build & push ingest Docker image"
	@echo "  make deploy      Build + terraform + dbt (full pipeline)"
	@echo "  make plan        Dry run (plan only, no build or apply)"
	@echo "  make destroy     Tear down all GCP resources"
	@echo "  make dbt-run     Run all dbt models (stg + mart)"
	@echo "  make dbt-stg     Run staging models only"
	@echo "  make dbt-test    Run dbt schema tests"
	@echo "  Image URI: $(IMAGE_URI)"
	@echo ""
