# ─────────────────────────────────────────────────────────────────────────
# ClimaSentinel Backend — Dockerfile
# ─────────────────────────────────────────────────────────────────────────
FROM python:3.11-slim

WORKDIR /app

# Install dependencies first (layer caching)
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY backend/app ./app

# Expose port (Railway uses $PORT env var)
EXPOSE 8000

# Run with uvicorn — Railway sets PORT automatically
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
