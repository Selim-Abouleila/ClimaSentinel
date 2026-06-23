# 8. Backend Architecture

The backend of ClimaSentinel is a modern, high-performance API designed to bridge the gap between our machine learning data warehouse and the user-facing frontend.

## Technology Stack
- **Framework**: FastAPI (Python 3.11)
- **Data Source**: Google BigQuery
- **Deployment**: Dockerized container running on Railway

## Architecture Overview

The backend acts as a lightweight serving layer. Rather than maintaining a separate relational database (like Postgres), we connected the backend directly to **Google BigQuery**. This serverless architecture is extremely cost-efficient and allows the backend to query the data engineering `dbt_marts` directly in real-time.

### Key Components

1. **FastAPI Application (`app/main.py`)**: 
   Provides automatic Swagger documentation (`/docs`), high-performance async request handling, and CORS configuration to allow the frontend to communicate securely.

2. **BigQuery Integration (`app/db.py`)**:
   Uses the official `google-cloud-bigquery` library. It authenticates using a Service Account JSON injected securely via environment variables.

3. **Endpoints**:
   - `GET /health`: Returns the health status and uptime of the backend. Used by Railway for deployment health checks.
   - `GET /data/current-scores`: Executes a SQL query against `mart_city_score_current` to fetch the latest Global Tipping Risk Scores for all cities and their Primary Risk Drivers.
   - `GET /data/history-scores`: Returns historical tipping scores from `mart_city_score_history`, optionally filtered by `city_id`.
   - `GET /data/current-zones`: Returns a zone summary (Stable / Monitoring / Tipping / Critical) from `mart_city_zone_current`.
   - `GET /data/city/{city_id}/scores`: Returns the five individual tipping sub-scores (**Heat, Wind, Rain, Air Quality, River/Flood**) for a single city from `mart_city_score_detail`. Returns `404` if the city is not found in the mart.

## Containerization
The backend is packaged using a `Dockerfile`. The Docker container uses a lightweight `python:3.11-slim` image, installs the `requirements.txt`, and uses `uvicorn` to serve the FastAPI application on port `8000`. Railway automatically detects this Dockerfile and deploys it natively.
