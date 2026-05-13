#!/bin/bash
# ═══════════════════════════════════════════════════════════════
# AgroSight AI — Production Backup Script
# ═══════════════════════════════════════════════════════════════
# Run via cron: 0 2 * * * /app/scripts/backup.sh
# Backs up:
#   - PostgreSQL database (pg_dump)
#   - MinIO buckets (mc mirror)
#   - Saved models (tar.gz)
#   - Uploads directory (rsync / tar)
#   - Local SQLite fallback (if used)
# ═══════════════════════════════════════════════════════════════

set -euo pipefail

# ── Configuration ──
BACKUP_DIR="${BACKUP_DIR:-/backups}"
RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-30}"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_NAME="agrosight_backup_${TIMESTAMP}"
BACKUP_PATH="${BACKUP_DIR}/${BACKUP_NAME}"

# Database
POSTGRES_HOST="${POSTGRES_HOST:-postgres}"
POSTGRES_DB="${POSTGRES_DB:-agrosight}"
POSTGRES_USER="${POSTGRES_USER:-agrosight}"
POSTGRES_PASSWORD="${POSTGRES_PASSWORD:-}"

# MinIO
MINIO_ENDPOINT="${MINIO_ENDPOINT:-http://minio:9000}"
MINIO_ACCESS_KEY="${MINIO_ACCESS_KEY:-agrosight}"
MINIO_SECRET_KEY="${MINIO_SECRET_KEY:-}"

# Notification (optional)
SLACK_WEBHOOK="${SLACK_WEBHOOK:-}"
ADMIN_EMAIL="${ADMIN_EMAIL:-admin@agrosight.ai}"

# ── Helpers ──
log() { echo "[backup] $(date '+%Y-%m-%d %H:%M:%S') $*"; }
error() { echo "[backup] ERROR: $*" >&2; }
notify() {
    if [[ -n "$SLACK_WEBHOOK" ]]; then
        curl -s -X POST -H 'Content-type: application/json' \
            --data "{\"text\":\"AgroSight AI Backup: $*\"}" \
            "$SLACK_WEBHOOK" > /dev/null || true
    fi
}

# ── Create backup directory ──
mkdir -p "$BACKUP_PATH"
log "Starting backup: $BACKUP_NAME"

# ── 1. PostgreSQL Database ──
log "Backing up PostgreSQL database..."
if command -v pg_dump >/dev/null 2>&1; then
    PGPASSWORD="$POSTGRES_PASSWORD" pg_dump \
        -h "$POSTGRES_HOST" \
        -U "$POSTGRES_USER" \
        -d "$POSTGRES_DB" \
        -F custom \
        -f "${BACKUP_PATH}/postgres_${POSTGRES_DB}_${TIMESTAMP}.dump"
    log "PostgreSQL backup completed"
else
    error "pg_dump not available — skipping PostgreSQL backup"
fi

# ── 2. MinIO Buckets ──
log "Backing up MinIO buckets..."
if command -v mc >/dev/null 2>&1; then
    mc alias set agrosight-minio "$MINIO_ENDPOINT" "$MINIO_ACCESS_KEY" "$MINIO_SECRET_KEY" > /dev/null 2>&1 || true
    mc mirror agrosight-minio/uploads "${BACKUP_PATH}/minio_uploads" > /dev/null 2>&1 || true
    mc mirror agrosight-minio/models "${BACKUP_PATH}/minio_models" > /dev/null 2>&1 || true
    mc mirror agrosight-minio/datasets "${BACKUP_PATH}/minio_datasets" > /dev/null 2>&1 || true
    mc mirror agrosight-minio/feedback "${BACKUP_PATH}/minio_feedback" > /dev/null 2>&1 || true
    log "MinIO backup completed"
else
    error "mc (MinIO client) not available — skipping MinIO backup"
fi

# ── 3. Saved Models ──
log "Backing up saved models..."
if [[ -d /app/saved_models ]]; then
    tar czf "${BACKUP_PATH}/saved_models_${TIMESTAMP}.tar.gz" -C /app saved_models/ 2>/dev/null || true
    log "Saved models backup completed"
else
    error "saved_models directory not found — skipping"
fi

# ── 4. Uploads Directory ──
log "Backing up uploads..."
if [[ -d /app/backend/uploads ]]; then
    tar czf "${BACKUP_PATH}/uploads_${TIMESTAMP}.tar.gz" -C /app/backend uploads/ 2>/dev/null || true
    log "Uploads backup completed"
else
    error "uploads directory not found — skipping"
fi

# ── 5. SQLite Fallback (if present) ──
log "Checking for SQLite fallback..."
if [[ -f /app/backend/instance/*.db ]]; then
    cp /app/backend/instance/*.db "${BACKUP_PATH}/" 2>/dev/null || true
    log "SQLite backup completed"
fi

# ── 6. Environment Config (sanitized) ──
log "Backing up environment config (sanitized)..."
env | grep -v -E 'PASSWORD|SECRET|KEY|TOKEN' | sort > "${BACKUP_PATH}/env_export.txt" 2>/dev/null || true

# ── 7. Compress full backup ──
log "Compressing backup archive..."
tar czf "${BACKUP_DIR}/${BACKUP_NAME}.tar.gz" -C "$BACKUP_DIR" "$BACKUP_NAME"
rm -rf "$BACKUP_PATH"

BACKUP_SIZE=$(du -h "${BACKUP_DIR}/${BACKUP_NAME}.tar.gz" | cut -f1)
log "Backup archive created: ${BACKUP_NAME}.tar.gz (${BACKUP_SIZE})"

# ── 8. Cleanup old backups ──
log "Cleaning up backups older than ${RETENTION_DAYS} days..."
find "$BACKUP_DIR" -name "agrosight_backup_*.tar.gz" -mtime +"$RETENTION_DAYS" -delete 2>/dev/null || true
log "Cleanup completed"

# ── 9. Verify backup integrity ──
log "Verifying backup integrity..."
if tar tzf "${BACKUP_DIR}/${BACKUP_NAME}.tar.gz" > /dev/null 2>&1; then
    log "Backup integrity verified successfully"
    notify "SUCCESS — Backup ${BACKUP_NAME} created (${BACKUP_SIZE})"
    exit 0
else
    error "Backup integrity check FAILED"
    notify "FAILED — Backup ${BACKUP_NAME} integrity check failed"
    exit 1
fi
