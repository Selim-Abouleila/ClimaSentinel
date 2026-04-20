output "cloud_run_job_name" {
  description = "Name of the Cloud Run ingest job"
  value       = google_cloud_run_v2_job.ingest.name
}

output "scheduler_job_name" {
  description = "Name of the Cloud Scheduler trigger"
  value       = google_cloud_scheduler_job.ingest_daily.name
}

output "artifact_registry_repo" {
  description = "Artifact Registry repo URI for pushing the ingest Docker image"
  value       = "${var.region}-docker.pkg.dev/${var.project_id}/clima-sentinel"
}

output "ingest_sa_email" {
  description = "Service account email used by the Cloud Run job"
  value       = google_service_account.ingest_sa.email
}
