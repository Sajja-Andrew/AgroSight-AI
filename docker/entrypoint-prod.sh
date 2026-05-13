#!/bin/bash
# AgroSight AI Production Entrypoint
# Handles database migrations, model loading, and application startup

set -e

echo "════════════════════════════════════════════════════════"
echo "AgroSight AI — Production Startup"
echo "════════════════════════════════════════════════════════"

# Create runtime directories
mkdir -p /app/backend/uploads /app/backend/instance /tmp/agrosight
chmod 755 /app/backend/uploads /tmp/agrosight

# Database initialization (Flask-SQLAlchemy)
echo "[entrypoint] Initializing database..."
cd /app/backend
python -c "
from app import app, db
with app.app_context():
    db.create_all()
    print('[entrypoint] Database tables created/verified')
" 2>&1 | tail -5

echo "[entrypoint] Environment:"
echo "  APP_ENV: ${APP_ENV:-production}"
echo "  PORT: ${PORT:-5000}"
echo "  DEBUG: ${DEBUG:-false}"

echo "[entrypoint] Starting application..."
exec "$@"
