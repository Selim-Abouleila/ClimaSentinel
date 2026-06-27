# 10. MLOps Monitoring Dashboard (Prometheus & Grafana)

This document explains the production monitoring architecture for ClimaSentinel, detailing how backend metrics are collected, stored, and visualized using Prometheus and Grafana. It also provides step-by-step instructions for running and verifying the monitoring stack locally.

---

## 🏛️ Architecture Overview

The monitoring pipeline follows a standard modern MLOps pull-based architecture:

```
[Live Python Backend] <───scrapes─── [Local Prometheus] <───queries─── [Local Grafana]
     (/metrics)                       (Time-Series DB)                (Visual Dashboard)
```

1. **Python Backend (`/metrics`)**: Exposes live application health, request counters, error rates, and prediction latencies using official Prometheus client libraries.
2. **Prometheus Scraper**: Wakes up every 15 seconds, reaches out to the backend's public `/metrics` endpoint, fetches the current metrics, and stores them in its time-series database.
3. **Grafana Dashboard**: Connects to Prometheus as a data source to render rich visual graphs and real-time alerts.

---

## 📊 Monitored Metrics

The dashboard tracks four core metrics essential for production machine learning systems:
- **Total Prediction Requests (`http_requests_total`)**: Measures the overall request volume hitting the model serving API.
- **Prediction Request Latency (`http_request_duration_seconds`)**: Measures the duration (in seconds) required to serve a prediction, ensuring SLAs are met.
- **Failed Requests (Error Rate)**: Tracks 4xx and 5xx HTTP response codes to monitor backend stability and data validation failures.
- **Backend Uptime / Health (`up`)**: Monitors whether the serving service is currently active and reachable.

---

## 💻 How to Run Monitoring Locally

Running Prometheus and Grafana locally is the recommended approach for development, testing, and presentations. It allows you to monitor live production traffic without incurring unnecessary cloud hosting costs.

### Prerequisites
- Make sure **Docker Desktop** is open and running on your machine.

### Step 1: Start the Monitoring Stack
Open your terminal (PowerShell), navigate to the `monitoring` directory, and launch the Docker Compose stack in the background:

```powershell
cd monitoring
docker compose up -d
```

### Step 2: Access the Services
Once the containers are successfully running, open the following URLs in your browser:

- **Grafana Dashboard**: [http://localhost:3000](http://localhost:3000)
  - *Authentication*: Anonymous access is enabled by default (`Viewer` role). You can view the dashboard instantly without logging in.
  - *Admin Login*: If you need to make edits to the dashboard panels, click **Sign In** in the top right. (Username: `admin` | Password: `admin`).
- **Prometheus UI**: [http://localhost:9090](http://localhost:9090)
  - *Target Status*: Open [http://localhost:9090/targets](http://localhost:9090/targets) to verify that Prometheus is successfully connecting to the live backend.

### Step 3: Generating Live Traffic
If your Grafana graphs show `No data`, it means the backend has not received any prediction requests recently. 
To populate the dashboard with real-time data:
1. Open your live Railway application (Frontend or Backend API) in a new browser tab.
2. Submit 5–10 prediction requests.
3. Return to Grafana, set the time window (top right) to **Last 5 minutes**, and watch the metrics populate instantly.

---

## 🛑 Stopping & Cleaning Up

When you are finished testing or presenting, you can stop the containers and completely free up your system resources.

To stop the containers:
```powershell
docker compose down
```

To stop the containers and delete the downloaded Docker images to save disk space:
```powershell
docker compose down --rmi all
```
