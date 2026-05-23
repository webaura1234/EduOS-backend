#!/bin/bash
# ──────────────────────────────────────────────
# EduOS Backend — Container Entrypoint
# ──────────────────────────────────────────────

set -e

echo "🔄 Waiting for database..."
python /app/deploy/scripts/wait_for_db.py

echo "🔄 Running migrations..."
python manage.py migrate --noinput

echo "🔄 Collecting static files..."
python manage.py collectstatic --noinput

echo "🚀 Starting server..."
exec "$@"
