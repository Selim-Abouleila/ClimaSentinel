# =============================================================================
# ClimaSentinel — Makefile
# =============================================================================
# Usage:
#   make bootstrap   → Create GCS Terraform state bucket & init backend
#   make deploy      → Terraform plan + apply (deploy GCP resources)
#   make plan        → Terraform plan only (dry run)
#   make destroy     → Terraform destroy (tear down all resources)
#   make help        → Show this help message
# =============================================================================

.PHONY: bootstrap deploy plan destroy help

TF_DIR := infra/terraform

## Initialise GCS state bucket and Terraform backend
bootstrap:
	@chmod +x infra/bootstrap.sh
	@bash infra/bootstrap.sh

## Deploy GCP resources (terraform plan + apply)
deploy:
	@terraform -chdir=$(TF_DIR) plan -out=tfplan
	@terraform -chdir=$(TF_DIR) apply tfplan

## Dry run — show what Terraform would change without applying
plan:
	@terraform -chdir=$(TF_DIR) plan

## Tear down all Terraform-managed GCP resources
destroy:
	@terraform -chdir=$(TF_DIR) destroy

## Show available commands
help:
	@echo ""
	@echo "  ClimaSentinel — Available commands"
	@echo "  ─────────────────────────────────────────"
	@echo "  make bootstrap   Init GCS state bucket & Terraform backend"
	@echo "  make deploy      Plan + apply GCP infrastructure"
	@echo "  make plan        Dry run (plan only, no apply)"
	@echo "  make destroy     Tear down all GCP resources"
	@echo ""
