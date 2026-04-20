# =============================================================================
# ClimaSentinel — Cloud Run Job + Cloud Scheduler
# =============================================================================

terraform {
  required_version = ">= 1.5"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}

# ─── Enable required APIs ──────────────────────────────────────────────────────
resource "google_project_service" "apis" {
  for_each = toset([
    "run.googleapis.com",
    "cloudscheduler.googleapis.com",
    "artifactregistry.googleapis.com",
    "bigquery.googleapis.com",
  ])
  service            = each.key
  disable_on_destroy = false
}

# ─── Service Account — runs the ingest job ────────────────────────────────────
resource "google_service_account" "ingest_sa" {
  account_id   = "ingest-sa"
  display_name = "ClimaSentinel Ingest Service Account"
  description  = "Used by the Cloud Run ingest job to write to BigQuery"
}

# Allow ingest SA to write data to BigQuery
resource "google_project_iam_member" "ingest_bq_editor" {
  project = var.project_id
  role    = "roles/bigquery.dataEditor"
  member  = "serviceAccount:${google_service_account.ingest_sa.email}"
}

# Allow ingest SA to run BigQuery jobs
resource "google_project_iam_member" "ingest_bq_job_user" {
  project = var.project_id
  role    = "roles/bigquery.jobUser"
  member  = "serviceAccount:${google_service_account.ingest_sa.email}"
}

# ─── Cloud Run Job — ingest container ─────────────────────────────────────────
resource "google_cloud_run_v2_job" "ingest" {
  name     = "clima-sentinel-ingest"
  location = var.region

  template {
    template {
      service_account = google_service_account.ingest_sa.email

      containers {
        image = var.ingest_image

        env {
          name  = "GCP_PROJECT_ID"
          value = var.project_id
        }
        env {
          name  = "BQ_DATASET_RAW"
          value = "raw"
        }
        env {
          name  = "GCP_REGION"
          value = var.region
        }

        resources {
          limits = {
            cpu    = "1"
            memory = "512Mi"
          }
        }
      }

      # Max runtime for the job (10 min is plenty for 10 cities)
      timeout = "600s"
    }
  }

  depends_on = [google_project_service.apis]
}

# ─── Service Account — Cloud Scheduler trigger ────────────────────────────────
resource "google_service_account" "scheduler_sa" {
  account_id   = "scheduler-sa"
  display_name = "ClimaSentinel Scheduler Service Account"
  description  = "Used by Cloud Scheduler to trigger the Cloud Run ingest job"
}

# Allow Scheduler SA to trigger Cloud Run jobs
resource "google_project_iam_member" "scheduler_run_invoker" {
  project = var.project_id
  role    = "roles/run.invoker"
  member  = "serviceAccount:${google_service_account.scheduler_sa.email}"
}

# ─── Cloud Scheduler — daily trigger at 06:00 UTC ────────────────────────────
resource "google_cloud_scheduler_job" "ingest_daily" {
  name             = "clima-sentinel-ingest-daily"
  description      = "Triggers the ClimaSentinel ingest Cloud Run job daily at 06:00 UTC"
  schedule         = var.ingest_schedule
  time_zone        = "UTC"
  attempt_deadline = "600s"
  region           = "europe-west1"  # Scheduler is not available in europe-west9

  http_target {
    http_method = "POST"
    uri = "https://${var.region}-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/${var.project_id}/jobs/${google_cloud_run_v2_job.ingest.name}:run"

    oauth_token {
      service_account_email = google_service_account.scheduler_sa.email
    }
  }

  depends_on = [
    google_project_service.apis,
    google_cloud_run_v2_job.ingest,
  ]
}
