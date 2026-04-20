# =============================================================================
# ClimaSentinel — Makefile
# =============================================================================
# Usage:
#   make bootstrap   → Create GCS Terraform state bucket & init backend
#   make build       → Build & push the ingest Docker image to Artifact Registry
#   make deploy      → Build image + terraform plan + apply
#   make plan        → Terraform plan only (dry run, no build)
#   make destroy     → Terraform destroy (tear down all resources)
#   make help        → Show this help message
# =============================================================================

.PHONY: bootstrap build deploy plan destroy help

TF_DIR := infra/terraform

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

## Build image then deploy GCP resources (terraform plan + apply)
deploy: build
	@terraform -chdir=$(TF_DIR) plan -out=tfplan \
		-var="project_id=$(GCP_PROJECT_ID)" \
		-var="region=$(GCP_REGION)" \
		-var="ingest_image=$(IMAGE_URI)"
	@terraform -chdir=$(TF_DIR) apply tfplan

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

## Show available commands
help:
	@echo ""
	@echo "  ClimaSentinel — Available commands"
	@echo "  ─────────────────────────────────────────"
	@echo "  make bootstrap   Init GCS state bucket & Terraform backend"
	@echo "  make build       Build & push ingest Docker image"
	@echo "  make deploy      Build image + plan + apply GCP infrastructure"
	@echo "  make plan        Dry run (plan only, no build or apply)"
	@echo "  make destroy     Tear down all GCP resources"
	@echo "  Image URI: $(IMAGE_URI)"
	@echo ""
