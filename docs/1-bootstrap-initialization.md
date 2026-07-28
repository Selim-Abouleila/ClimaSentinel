# 1. Bootstrap Initialization Guide

This document describes how to clone the ClimaSentinel repository into GCP Cloud Shell and initialize the Terraform remote state backend on Google Cloud Storage (GCS).

---

## Prerequisites

Before you begin, ensure the following conditions are met:

| Requirement | Details |
|---|---|
| GCP Project | An active GCP project with billing enabled |
| IAM Permissions | A deployer identity that can enable services; manage the Terraform state bucket and Artifact Registry; submit Cloud Build builds; create service accounts and project IAM bindings; manage Cloud Run Jobs and Cloud Scheduler; and create/query BigQuery datasets and tables |
| Tools | `gcloud` CLI and `terraform` — both pre-installed in Cloud Shell |

The exact predefined roles depend on your organization's IAM policy. `Storage
Admin` and `Service Usage Admin` alone are **not** sufficient for the complete
bootstrap and deploy flow. Prefer a dedicated deployer identity with the
smallest custom-role permissions that cover the capabilities above; ask a GCP
administrator to provision it rather than granting broad permanent access to
an individual account.

---

## Step 1 — Open Cloud Shell

From the [GCP Console](https://console.cloud.google.com), click the **Activate Cloud Shell** button (terminal icon) in the top-right toolbar.

Once the terminal is ready, authenticate if prompted:

```bash
gcloud auth login
```

---

## Step 2 — Clone the Repository

```bash
git clone https://github.com/Selim-Abouleila/ClimaSentinel.git
cd ClimaSentinel
```

---

## Step 3 — Initialize the Environment File

The `.env` file is **gitignored** and must be created locally from the provided template.

```bash
cp .env.example .env
```

Open the file and fill in your GCP Project ID:

```bash
nano .env
```

The file looks like this — only `GCP_PROJECT_ID` needs to be changed:

```dotenv
GCP_PROJECT_ID=your-gcp-project-id   # ← replace this
GCP_REGION=europe-west9               # pre-configured (Paris region)
TF_STATE_BUCKET=                      # optional — defaults to <project-id>-tf-state
```

Save and exit: `Ctrl+O` → `Enter` → `Ctrl+X`

---

## Step 4 — Bootstrap the Terraform State Backend

Run the bootstrap via the Makefile:

```bash
make bootstrap
```

This runs `infra/bootstrap.sh` under the hood and will:

1. Source your `.env` variables automatically
2. Set the active GCP project via `gcloud`
3. Enable the Storage, Resource Manager, Artifact Registry, Cloud Run,
   Scheduler, BigQuery and Cloud Build APIs
4. Create the Artifact Registry Docker repository (skips if already exists)
5. Create the GCS bucket for Terraform remote state (skips if already exists)
6. Enable **object versioning** on the bucket
7. Attempt to apply a **30-day retention policy** (warns and continues if the
   organization policy does not permit it)
8. Enforce **uniform bucket-level access** (no public access)
9. Generate `infra/terraform/backend.tf` pointing at the bucket
10. Run `terraform init` to wire up the remote backend when Terraform is
    available
11. Add a persistent `bq` alias with a 1 GiB query cap to `~/.bashrc`

You will be prompted to confirm before any GCP resources are created:

```
[INFO]  Project  : my-project-id
[INFO]  Region   : europe-west9
[INFO]  Bucket   : gs://my-project-id-tf-state

Proceed? [y/N]
```

---

## Step 5 — Prepare BigQuery

The current Terraform configuration does not create BigQuery datasets, and the
ingestion loader creates tables only inside an existing dataset. Create the
`raw` dataset once, in the same location configured by `GCP_REGION`:

```bash
set -a
source .env
set +a
bq --location="$GCP_REGION" mk --dataset "$GCP_PROJECT_ID:raw"
```

If the dataset already exists, verify its location instead of recreating it:

```bash
bq show --format=prettyjson "$GCP_PROJECT_ID:raw"
```

The `stg` and `mart` datasets are created by dbt when their first relations are
built.

---

## Step 6 — Deploy GCP Resources

Once the backend is initialized, deploy your infrastructure:

```bash
make deploy
```

`make deploy` is a mutating, non-interactive pipeline. In order, it:

1. builds and pushes the ingestion image through Cloud Build;
2. creates a saved Terraform plan and immediately applies it without an
   additional confirmation prompt;
3. installs the dbt dependencies in the current Python environment;
4. runs `dbt seed`, `dbt run`, and `dbt test`.

Run `make plan` first when you want to review Terraform changes before allowing
those mutations:

```bash
make plan
```

### First deployment into an empty project

The current `make deploy` order is not fully clean-room-safe. Terraform creates
the Cloud Run Job before dbt runs, but the four active `raw.*` source tables do
not exist until that job completes its first ingestion. Consequently, the
first `make deploy` can apply the infrastructure successfully and then fail in
`dbt run` because the source tables are absent.

After that initial infrastructure apply, execute the job once and wait for it:

```bash
gcloud run jobs execute clima-sentinel-ingest \
  --region="$GCP_REGION" \
  --project="$GCP_PROJECT_ID" \
  --wait
```

Confirm in the Cloud Run logs that both ingestion and `dbt run` completed, then
run the warehouse tests explicitly:

```bash
make dbt-test
```

### All available commands

| Command | Description |
|---|---|
| `make bootstrap` | Create GCS state bucket & init Terraform backend |
| `make build` | Build and push the ingestion image through Cloud Build |
| `make deploy` | Build/push + non-interactive Terraform apply + dbt seed/run/test |
| `make plan` | Dry run — show changes without applying |
| `make destroy` | Destroy only Terraform-managed resources |
| `make dbt-run` | Run all staging and mart models |
| `make dbt-stg` | Run staging models only |
| `make dbt-test` | Run dbt schema and singular tests |

---

## Step 7 — Verify

Confirm the bucket was created and versioning is active:

```bash
set -a
source .env
set +a
STATE_BUCKET="${TF_STATE_BUCKET:-${GCP_PROJECT_ID}-tf-state}"
gsutil ls "gs://$STATE_BUCKET"
gsutil versioning get "gs://$STATE_BUCKET"
```

Expected output:

```
gs://my-project-id-tf-state/
gs://my-project-id-tf-state: Enabled
```

Confirm the Terraform backend is initialized:

```bash
cat infra/terraform/backend.tf
terraform -chdir=infra/terraform show
```

---

## Project Structure Reference

```
ClimaSentinel/
├── .env.example          # Template — committed to git
├── .env                  # Your secrets — gitignored, never committed
├── .gitignore
├── Makefile              # make bootstrap | make deploy | make plan | make destroy
├── infra/
│   ├── bootstrap.sh      # Called by make bootstrap
│   └── terraform/
│       └── backend.tf    # Auto-generated by make bootstrap
├── ingest/               # Python batch job (Open-Meteo API calls)
├── config/               # cities.csv
└── docs/
    └── 1-bootstrap-initialization.md # This document
```

---

## Troubleshooting

**`.env` not found warning**
> The script will warn if `.env` is missing. Run `cp .env.example .env` and retry.

**Bucket already exists**
> The script detects this and skips creation — no action needed.

**Insufficient permissions**
> The full flow needs more than storage and service-usage permissions. Ask your
> GCP administrator for a deployer identity covering Artifact Registry, Cloud
> Build, service-account/IAM administration, Cloud Run, Scheduler and BigQuery.

**`make destroy` left resources behind**
> This is expected with the current infrastructure split. It removes resources
> tracked in Terraform state, but not the bootstrap-created GCS state bucket or
> Artifact Registry repository, BigQuery datasets/tables created outside
> Terraform, or enabled project APIs. Review and remove those separately only
> when their data and retained state are no longer needed.

**`terraform` not found**
> Cloud Shell includes Terraform by default. If missing, install it via [HashiCorp's instructions](https://developer.hashicorp.com/terraform/install).
