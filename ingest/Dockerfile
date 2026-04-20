FROM python:3.12-slim

WORKDIR /app

# Install dependencies
COPY ingest/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy ingest source
COPY ingest/ ./ingest/

# Copy city config
COPY config/cities.csv ./config/cities.csv

WORKDIR /app/ingest

CMD ["python", "main.py"]
