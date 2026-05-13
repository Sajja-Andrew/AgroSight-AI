#!/bin/bash
# ═══════════════════════════════════════════════════════════════
# AgroSight AI — Docker Entrypoint
# ═══════════════════════════════════════════════════════════════
# Initializes runtime environment before Supervisor takes over.
# ═══════════════════════════════════════════════════════════════

set -euo pipefail

echo ""
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║            AgroSight AI — Production Startup                  ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""

# ── Create runtime directories (ignore failures on read-only fs) ──
mkdir -p /run/agrosight /var/log/supervisor /var/log/nginx /var/cache/nginx 2>/dev/null || true
chown -R agrosight:agrosight /run/agrosight /var/log/supervisor /var/log/nginx /var/cache/nginx 2>/dev/null || true
chmod 755 /run/agrosight 2>/dev/null || true

# ── Set correct permissions for Unix sockets directory ──
chmod 777 /run/agrosight 2>/dev/null || true

# ── Create backend upload/instance dirs ──
mkdir -p /app/backend/uploads /app/backend/instance
chown -R agrosight:agrosight /app/backend/uploads /app/backend/instance

# ── Wait for PostgreSQL (if DATABASE_URL points to Postgres) ──
if [[ "${DATABASE_URL:-}" == postgresql* ]]; then
    echo "[entrypoint] Waiting for PostgreSQL..."
    host=$(echo "$DATABASE_URL" | sed -n 's/.*@\([^:/]*\).*/\1/p')
    port=$(echo "$DATABASE_URL" | sed -n 's/.*:\([0-9]*\)\/.*/\1/p')
    port=${port:-5432}

    for i in {1..30}; do
        if nc -z "$host" "$port" 2>/dev/null; then
            echo "[entrypoint] PostgreSQL is ready at $host:$port"
            break
        fi
        echo "[entrypoint] PostgreSQL not ready yet (attempt $i/30)..."
        sleep 2
    done
fi

# ── Wait for MinIO (if configured) ──
if [[ -n "${MINIO_ENDPOINT:-}" && "${MINIO_ENDPOINT}" != *"127.0.0.1"* && "${MINIO_ENDPOINT}" != *"localhost"* ]]; then
    echo "[entrypoint] Waiting for MinIO..."
    host=$(echo "$MINIO_ENDPOINT" | sed -n 's|http[s]*://\([^:/]*\).*|\1|p')
    port=$(echo "$MINIO_ENDPOINT" | sed -n 's|http[s]*://[^:]*:\([0-9]*\).*|\1|p')
    port=${port:-9000}

    for i in {1..30}; do
        if nc -z "$host" "$port" 2>/dev/null; then
            echo "[entrypoint] MinIO is ready at $host:$port"
            break
        fi
        echo "[entrypoint] MinIO not ready yet (attempt $i/30)..."
        sleep 2
    done
fi

# ── Run database migrations (Alembic) ──
if [[ -d /app/backend/migrations ]]; then
    echo "[entrypoint] Running database migrations..."
    cd /app/backend/migrations
    # Use alembic directly to avoid heavy TensorFlow app imports via Flask CLI
    DATABASE_URL="${DATABASE_URL:-}" alembic -c alembic.ini upgrade head || echo "[entrypoint] Migration skipped or already up-to-date"
else
    echo "[entrypoint] No migrations directory found. Skipping migrations."
fi

# ── Initialize MinIO buckets (if Python script exists) ──
if [[ -f /app/scripts/init-minio.py ]]; then
    echo "[entrypoint] Initializing MinIO buckets..."
    python /app/scripts/init-minio.py || echo "[entrypoint] MinIO init skipped or already done"
fi

# ── Ensure Nginx log files exist (ignore failures on read-only fs) ──
touch /var/log/nginx/access.log /var/log/nginx/error.log 2>/dev/null || true
chown agrosight:agrosight /var/log/nginx/access.log /var/log/nginx/error.log 2>/dev/null || true

# ── Print environment summary ──
echo ""
echo "[entrypoint] Environment Summary:"
echo "  APP_ENV         = ${APP_ENV:-production}"
echo "  PORT            = ${PORT:-8080}"
echo "  DATABASE_URL    = ${DATABASE_URL:-NOT SET}"
echo "  MINIO_ENDPOINT  = ${MINIO_ENDPOINT:-NOT SET}"
echo "  GUNICORN_WORKERS= ${GUNICORN_WORKERS:-2}"
echo "  NODE_ENV        = ${NODE_ENV:-production}"
echo ""
echo "[entrypoint] Starting application..."

echo ""

# ── Pass control to Supervisor (or whatever CMD was provided) ──
exec "$@"
