FROM python:3.11-slim

WORKDIR /app

# Install system dependencies for psycopg2, git, etc.
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    git \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for layer caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Railway injects $PORT at runtime (defaults to 8080)
ENV PORT=8080

EXPOSE ${PORT}

CMD uvicorn api:app --host 0.0.0.0 --port ${PORT}
