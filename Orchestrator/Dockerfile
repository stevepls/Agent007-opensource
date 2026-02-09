FROM python:3.12-slim

WORKDIR /app

# Install system deps for psycopg2-binary etc.
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev git && \
    rm -rf /var/lib/apt/lists/*

# Install Python deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Railway injects $PORT at runtime (default 8502 for local dev)
ENV PORT=8502

EXPOSE ${PORT}

CMD uvicorn api:app --host 0.0.0.0 --port ${PORT}
