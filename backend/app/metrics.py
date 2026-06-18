"""
Prometheus metrics for monitoring.

Exposes:
  - prediction_requests_total   (Counter)
  - prediction_latency_seconds  (Histogram)
  - prediction_errors_total     (Counter)
  - app_info                    (Info — uptime, version)
"""

from prometheus_client import (
    Counter,
    Histogram,
    Info,
    generate_latest,
    CONTENT_TYPE_LATEST,
)

# ── Metrics ──────────────────────────────────────────────────────────────

REQUEST_COUNT = Counter(
    "prediction_requests_total",
    "Total number of prediction requests",
    ["city", "status"],
)

REQUEST_LATENCY = Histogram(
    "prediction_latency_seconds",
    "Time spent processing prediction requests",
    ["city"],
    buckets=[0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0],
)

ERROR_COUNT = Counter(
    "prediction_errors_total",
    "Total number of failed prediction requests",
    ["city", "error_type"],
)

APP_INFO = Info(
    "climasentinel_backend",
    "Backend application info",
)


def get_metrics() -> tuple[bytes, str]:
    """Return serialised Prometheus metrics and content type."""
    return generate_latest(), CONTENT_TYPE_LATEST
