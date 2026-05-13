#!/bin/bash
# ═══════════════════════════════════════════════════════════════
# AgroSight AI — Health Monitoring & Alerting Script
# ═══════════════════════════════════════════════════════════════
# Run via cron every minute:
#   * * * * * /app/scripts/monitor.sh
#
# Checks:
#   - API health endpoint
#   - PostgreSQL connectivity
#   - MinIO health
#   - Redis connectivity
#   - Disk space
#   - Memory usage
# ═══════════════════════════════════════════════════════════════

set -euo pipefail

# ── Configuration ──
APP_URL="${APP_URL:-http://localhost:8080}"
POSTGRES_HOST="${POSTGRES_HOST:-postgres}"
POSTGRES_DB="${POSTGRES_DB:-agrosight}"
POSTGRES_USER="${POSTGRES_USER:-agrosight}"
POSTGRES_PASSWORD="${POSTGRES_PASSWORD:-}"
MINIO_URL="${MINIO_URL:-http://minio:9000/minio/health/live}"
REDIS_HOST="${REDIS_HOST:-redis}"
DISK_THRESHOLD="${DISK_THRESHOLD:-90}"
MEMORY_THRESHOLD="${MEMORY_THRESHOLD:-95}"
SLACK_WEBHOOK="${SLACK_WEBHOOK:-}"

# ── State file (prevents alert spam) ──
STATE_DIR="/tmp/agrosight-monitor"
mkdir -p "$STATE_DIR"

# ── Helpers ──
log() { echo "[monitor] $(date '+%Y-%m-%d %H:%M:%S') $*"; }
alert() {
    log "ALERT: $*"
    if [[ -n "$SLACK_WEBHOOK" ]]; then
        curl -s -X POST -H 'Content-type: application/json' \
            --data "{\"text\":\"AgroSight AI ALERT: $*\"}" \
            "$SLACK_WEBHOOK" > /dev/null 2>&1 || true
    fi
}
state_file() { echo "$STATE_DIR/$1.alert"; }

# Check if alert was already sent (cooldown = 10 min)
alert_sent() { [[ -f "$(state_file "$1")" ]] && [[ $(find "$(state_file "$1")" -mmin -10) ]]; }
mark_alert() { touch "$(state_file "$1")"; }
clear_alert() { rm -f "$(state_file "$1")"; }

# ── 1. API Health ──
if ! curl -fsS "${APP_URL}/api/health" > /dev/null 2>&1; then
    if ! alert_sent api; then
        alert "API health check FAILED on ${APP_URL}/api/health"
        mark_alert api
    fi
else
    clear_alert api
fi

# ── 2. PostgreSQL ──
if ! PGPASSWORD="$POSTGRES_PASSWORD" pg_isready -h "$POSTGRES_HOST" -U "$POSTGRES_USER" -d "$POSTGRES_DB" > /dev/null 2>&1; then
    if ! alert_sent postgres; then
        alert "PostgreSQL connectivity FAILED on $POSTGRES_HOST"
        mark_alert postgres
    fi
else
    clear_alert postgres
fi

# ── 3. MinIO ──
if ! curl -fsS "$MINIO_URL" > /dev/null 2>&1; then
    if ! alert_sent minio; then
        alert "MinIO health check FAILED on $MINIO_URL"
        mark_alert minio
    fi
else
    clear_alert minio
fi

# ── 4. Redis ──
if ! redis-cli -h "$REDIS_HOST" ping > /dev/null 2>&1; then
    if ! alert_sent redis; then
        alert "Redis connectivity FAILED on $REDIS_HOST"
        mark_alert redis
    fi
else
    clear_alert redis
fi

# ── 5. Disk Space ──
DISK_USAGE=$(df / | tail -1 | awk '{print $5}' | tr -d '%')
if [[ "$DISK_USAGE" -gt "$DISK_THRESHOLD" ]]; then
    if ! alert_sent disk; then
        alert "Disk usage CRITICAL: ${DISK_USAGE}% (threshold: ${DISK_THRESHOLD}%)"
        mark_alert disk
    fi
else
    clear_alert disk
fi

# ── 6. Memory ──
MEMORY_USAGE=$(free | awk '/Mem:/ {printf "%.0f", $3/$2 * 100}')
if [[ "$MEMORY_USAGE" -gt "$MEMORY_THRESHOLD" ]]; then
    if ! alert_sent memory; then
        alert "Memory usage CRITICAL: ${MEMORY_USAGE}% (threshold: ${MEMORY_THRESHOLD}%)"
        mark_alert memory
    fi
else
    clear_alert memory
fi

log "Health check cycle completed"
