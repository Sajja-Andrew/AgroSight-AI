#!/bin/bash
# ═══════════════════════════════════════════════════════════════
# AgroSight AI — PostgreSQL Container Init Script
# ═══════════════════════════════════════════════════════════════
# Runs inside the Postgres container on first startup.
# Creates databases, users, and applies optimizations.
# ═══════════════════════════════════════════════════════════════

set -euo pipefail

DB_NAME="${POSTGRES_DB:-agrosight}"
DB_USER="${POSTGRES_USER:-agrosight}"

echo "[init-db] Initializing PostgreSQL for AgroSight AI..."

# The init scripts run as the postgres superuser by default,
# so we can configure the database directly.

# Set connection limits and performance settings
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$DB_NAME" <<-EOSQL
    -- Optimize for web workload
    ALTER SYSTEM SET max_connections = '200';
    ALTER SYSTEM SET shared_buffers = '256MB';
    ALTER SYSTEM SET effective_cache_size = '768MB';
    ALTER SYSTEM SET maintenance_work_mem = '64MB';
    ALTER SYSTEM SET checkpoint_completion_target = '0.9';
    ALTER SYSTEM SET wal_buffers = '16MB';
    ALTER SYSTEM SET default_statistics_target = '100';
    ALTER SYSTEM SET random_page_cost = '1.1';
    ALTER SYSTEM SET effective_io_concurrency = '200';
    ALTER SYSTEM SET work_mem = '655kB';
    ALTER SYSTEM SET min_wal_size = '1GB';
    ALTER SYSTEM SET max_wal_size = '4GB';
    ALTER SYSTEM SET log_checkpoints = 'on';
    ALTER SYSTEM SET log_connections = 'on';
    ALTER SYSTEM SET log_disconnections = 'on';
    ALTER SYSTEM SET log_lock_waits = 'on';
    ALTER SYSTEM SET log_temp_files = '0';
    ALTER SYSTEM SET log_autovacuum_min_duration = '0';
    ALTER SYSTEM SET autovacuum_max_workers = '4';

    -- Apply changes
    SELECT pg_reload_conf();
EOSQL

echo "[init-db] PostgreSQL tuned for AgroSight AI workload."
