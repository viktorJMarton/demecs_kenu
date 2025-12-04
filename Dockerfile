# Use Python 3.11 slim image
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY flaskr/ ./flaskr/
COPY init_db.py .
COPY .env .

# Create directories for uploads and database
RUN mkdir -p public/uploads

# Initialize database
RUN python init_db.py

# Expose port
EXPOSE 8000

# Run with gunicorn: reduce workers and use thread workers to lower memory pressure
# Use a small worker count and threads so the container doesn't OOM on low-memory VPS
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "2", "-k", "gthread", "--threads", "3", "--timeout", "120", "--max-requests", "200", "--max-requests-jitter", "50", "--access-logfile", "/app/logs/access.log", "--error-logfile", "/app/logs/error.log", "--log-level", "info", "flaskr:create_app()"]
