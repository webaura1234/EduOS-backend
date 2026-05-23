# ──────────────────────────────────────────────
# EduOS Backend — Dockerfile
# Multi-stage build for production deployment
# ──────────────────────────────────────────────

# Stage 1: Base
FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# System dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Stage 2: Dependencies
FROM base AS deps

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Stage 3: Application
FROM deps AS app

COPY . .

# Collect static files
RUN python manage.py collectstatic --noinput || true

# Create non-root user
RUN addgroup --system eduos && \
    adduser --system --ingroup eduos eduos
USER eduos

EXPOSE 8000

# Default: run with gunicorn
CMD ["gunicorn", "config.wsgi:application", \
     "--bind", "0.0.0.0:8000", \
     "--workers", "4", \
     "--timeout", "120", \
     "--access-logfile", "-"]
