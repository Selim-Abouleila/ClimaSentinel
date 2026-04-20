variable "project_id" {
  description = "GCP project ID"
  type        = string
}

variable "region" {
  description = "GCP region for all resources"
  type        = string
  default     = "europe-west9"
}

variable "ingest_image" {
  description = "Full Artifact Registry image URI for the ingest job"
  type        = string
  # Format: europe-west9-docker.pkg.dev/<project_id>/clima-sentinel/ingest:latest
  # Populated after first `docker build && docker push`
}

variable "ingest_schedule" {
  description = "Cron schedule for the Cloud Scheduler trigger (UTC)"
  type        = string
  default     = "0 6 * * *"  # daily at 06:00 UTC
}
