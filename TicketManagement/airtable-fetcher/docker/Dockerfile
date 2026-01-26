FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY src/requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY src/ .

# Create output directory
RUN mkdir -p /app/output

# Make script executable
RUN chmod +x fetch_airtable_tickets.py

# Create non-root user for security
RUN groupadd -r airtable && useradd -r -g airtable airtable
RUN chown -R airtable:airtable /app
USER airtable

# Default command
CMD ["python", "fetch_airtable_tickets.py", "--help"] 