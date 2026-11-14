FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends gcc \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.lock requirements.txt ./
RUN python -m pip install --no-cache-dir -r requirements.lock

COPY flaskr/ ./flaskr/
COPY init_db.py ./

RUN mkdir -p /app/public/uploads /app/logs /app/instance/cache

EXPOSE 8000

CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "2", "-k", "gthread", "--threads", "100", "--timeout", "120", "--max-requests", "200", "--max-requests-jitter", "50", "--access-logfile", "/app/logs/access.log", "--error-logfile", "/app/logs/error.log", "--log-level", "info", "flaskr:create_app()"]
