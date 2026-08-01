# 1. Bootstrap Initialization Guide

This document describes how to clone the ClimaSentinel repository into GCP Cloud Shell and initialize the Terraform remote state backend on Google Cloud Storage (GCS).

---

## Prerequisites

Before you begin, ensure the following conditions are met:

| Requirement | Details |
|---|---|
| GCP Project | An active GCP project with billing enabled |
| IAM Permissions | A deployer identity that can enable services; manage the Terraform state bucket and Artifact Registry; submit Cloud Build builds; create service accounts and project IAM bindings; manage Cloud Run Jobs and Cloud Scheduler; and create/query BigQuery datasets and tables |
| Tools | `git`, `gcloud`, `gsutil` and `bq`; Terraform `>= 1.5` is required to complete backend initialization, planning and deployment |

The exact predefined roles depend on your organization's IAM policy. `Storage
Admin` and `Service Usage Admin` alone are **not** sufficient for the complete
bootstrap and deploy flow. Prefer a dedicated deployer identity with the
smallest custom-role permissions that cover the capabilities above; ask a GCP
administrator to provision it rather than granting broad permanent access to
an individual account.

---

## Step 1 — Open Cloud Shell

From the [GCP Console](https://console.cloud.google.com), click the **Activate Cloud Shell** button (terminal icon) in the top-right toolbar.

Once the terminal is ready, confirm the active CLI identity and initialize
Application Default Credentials (ADC). The first identity is used by `gcloud`;
ADC is used by local dbt/BigQuery clients.

```bash
gcloud auth list
gcloud auth application-default login
terraform version
```

Cloud Shell provides the Google Cloud CLI, but Terraform availability is not a
repository guarantee. If the final command is unavailable, the bootstrap script
can still create its GCP resources and write `backend.tf`; install Terraform
before completing backend initialization, planning or deployment.

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

The committed template looks like this. For the standard layout, replace
`GCP_PROJECT_ID`; change the region or dataset names only when the deployment is
intentionally using a different layout.

```dotenv
GCP_PROJECT_ID=your-gcp-project-id   # ← replace this
GCP_REGION=europe-west9               # pre-configured (Paris region)
BQ_DATASET=mart                        # backend/model extraction default
BQ_STAGING_DATASET=stg                 # backend seed lookup default
TF_STATE_BUCKET=                      # optional — defaults to <project-id>-tf-state
```

`BQ_DATASET` and `BQ_STAGING_DATASET` configure application queries. The dbt
schemas remain explicitly configured as `stg` and `mart` in
`transform/dbt_project.yml`; changing only these two environment variables does
not move dbt relations.

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

If Terraform is missing, the script can still create bootstrap resources and
write `backend.tf`, but it skips backend initialization. Installing Terraform
later through `make deploy` does not retroactively run `terraform init`; run the
following before planning or deploying:

```bash
terraform -chdir=infra/terraform init
```

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

1. validates `config/cities.csv`, the monthly normals seed, and the frozen
   forecast-city allowlist;
2. builds and pushes the ingestion image through Cloud Build;
3. creates a saved Terraform plan and immediately applies it without an
   additional confirmation prompt;
4. executes the updated `clima-sentinel-ingest` Cloud Run Job with `--wait`;
   that job loads Bronze rows and runs its embedded `dbt seed` + `dbt run`;
5. installs the dbt dependencies in the current Python environment; and
6. runs a final `dbt seed`, `dbt run`, and `dbt test` from the deployer.

Run `make plan` first when you want to review Terraform changes before allowing
those mutations:

```bash
make plan
```

### First deployment into an empty project

Create the `raw` dataset in Step 5 before the first deploy. With that
prerequisite satisfied, the deploy flow waits for ingestion to create the four
active raw tables before its final dbt build and tests. No separate manual job
execution is required.

The ingestion runner preserves successfully inserted raw rows but exits
non-zero if any city/source pair fails or if its embedded `dbt seed`/`dbt run`
fails. Because `gcloud run jobs execute ... --wait` is part of `make deploy`,
either condition stops the deployment before the final local dbt validation.

`make deploy` does not publish the FastAPI backend or Next.js frontend hosted
on Railway. After this GCP data deployment succeeds, promote the reviewed
commit from `dev` to `staging` to trigger the Railway application deployment
and its live end-to-end check.

### All available commands

| Command | Description |
|---|---|
| `make bootstrap` | Create GCS state bucket & init Terraform backend |
| `make build` | Build and push the ingestion image through Cloud Build |
| `make validate-cities` | Validate city registry, monthly-normal completeness, and frozen forecast scope |
| `make deploy` | Validate + build/push + Terraform apply + waited ingestion + dbt seed/run/test |
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
├── Makefile              # validate, bootstrap, deploy, plan and dbt commands
├── infra/
│   ├── bootstrap.sh      # Called by make bootstrap
│   └── terraform/
│       └── backend.tf    # Auto-generated by make bootstrap
├── ingest/               # Python batch job (Open-Meteo API calls)
├── config/               # cities.csv
├── scripts/              # City configuration validator used by CI/deploy
├── transform/            # dbt models, seeds, tests and normals generator
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
> Install Terraform `>= 1.5` via
> [HashiCorp's instructions](https://developer.hashicorp.com/terraform/install),
> then run `terraform -chdir=infra/terraform init`. The Makefile's deploy-time
> installer does not initialize a backend that bootstrap previously skipped.
