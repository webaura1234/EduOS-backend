#!/bin/bash
# ──────────────────────────────────────────────
# Wait for PostgreSQL to be ready
# ──────────────────────────────────────────────

set -e

host="${DB_HOST:-localhost}"
port="${DB_PORT:-5432}"

echo "Waiting for PostgreSQL at $host:$port..."

while ! pg_isready -h "$host" -p "$port" -q 2>/dev/null; do
    echo "PostgreSQL is unavailable - sleeping"
    sleep 1
done

echo "PostgreSQL is ready!"
