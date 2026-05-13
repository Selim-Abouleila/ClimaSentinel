FROM python:3.12-slim

WORKDIR /app

# Install ingest dependencies
COPY ingest/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install dbt dependencies
COPY transform/requirements.txt ./transform-requirements.txt
RUN pip install --no-cache-dir -r transform-requirements.txt

# Copy ingest source
COPY ingest/ ./ingest/

# Copy city config
COPY config/cities.csv ./config/cities.csv

# Copy dbt project (models, seeds, profiles)
COPY transform/ ./transform/

WORKDIR /app/ingest

CMD ["python", "main.py"]
