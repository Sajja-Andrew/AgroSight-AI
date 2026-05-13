#!/bin/bash
# ═══════════════════════════════════════════════════════════════
# AgroSight AI — Production Restore Script
# ═══════════════════════════════════════════════════════════════
# Restores from a backup archive created by backup.sh.
# Usage: ./restore.sh <backup_archive.tar.gz>
# ═══════════════════════════════════════════════════════════════

set -euo pipefail

# ── Configuration ──
BACKUP_DIR="${BACKUP_DIR:-/backups}"
RESTORE_DIR="${RESTORE_DIR:-/tmp/restore_$$}"

# Database
POSTGRES_HOST="${POSTGRES_HOST:-postgres}"
POSTGRES_DB="${POSTGRES_DB:-agrosight}"
POSTGRES_USER="${POSTGRES_USER:-agrosight}"
POSTGRES_PASSWORD="${POSTGRES_PASSWORD:-}"

# MinIO
MINIO_ENDPOINT="${MINIO_ENDPOINT:-http://minio:9000}"
MINIO_ACCESS_KEY="${MINIO_ACCESS_KEY:-agrosight}"
MINIO_SECRET_KEY="${MINIO_SECRET_KEY:-}"

# ── Helpers ──
log() { echo "[restore] $(date '+%Y-%m-%d %H:%M:%S') $*"; }
error() { echo "[restore] ERROR: $*" >&2; }

# ── Validate arguments ──
if [[ $# -lt 1 ]]; then
    error "Usage: $0 <backup_archive.tar.gz>"
    exit 1
fi

ARCHIVE="$1"
if [[ ! -f "$ARCHIVE" ]]; then
    error "Archive not found: $ARCHIVE"
    exit 1
fi

log "Starting restore from: $ARCHIVE"

# ── Extract archive ──
mkdir -p "$RESTORE_DIR"
tar xzf "$ARCHIVE" -C "$RESTORE_DIR"
EXTRACTED_DIR=$(find "$RESTORE_DIR" -maxdepth 1 -type d | tail -n 1)
log "Extracted to: $EXTRACTED_DIR"

# ── 1. Restore PostgreSQL ──
log "Restoring PostgreSQL database..."
DUMP_FILE=$(find "$EXTRACTED_DIR" -name "postgres_*.dump" | head -n 1)
if [[ -n "$DUMP_FILE" ]]; then
    PGPASSWORD="$POSTGRES_PASSWORD" pg_restore \
        -h "$POSTGRES_HOST" \
        -U "$POSTGRES_USER" \
        -d "$POSTGRES_DB" \
        --clean --if-exists \
        "$DUMP_FILE" 2>/dev/null || \
    PGPASSWORD="$POSTGRES_PASSWORD" pg_restore \
        -h "$POSTGRES_HOST" \
        -U "$POSTGRES_USER" \
        -d "$POSTGRES_DB" \
        --no-owner --no-privileges \
        "$DUMP_FILE"
    log "PostgreSQL restore completed"
else
    error "PostgreSQL dump not found in archive — skipping"
fi

# ── 2. Restore MinIO Buckets ──
log "Restoring MinIO buckets..."
if command -v mc >/dev/null 2>&1; then
    mc alias set agrosight-minio "$MINIO_ENDPOINT" "$MINIO_ACCESS_KEY" "$MINIO_SECRET_KEY" > /dev/null 2>&1 || true
    for bucket_dir in "$EXTRACTED_DIR"/minio_*; do
        if [[ -d "$bucket_dir" ]]; then
            bucket_name=$(basename "$bucket_dir" | sed 's/minio_//')
            mc mirror --overwrite --remove "$bucket_dir" "agrosight-minio/$bucket_name" > /dev/null 2>&1 || true
            log "Restored MinIO bucket: $bucket_name"
        fi
    done
else
    error "mc (MinIO client) not available — skipping MinIO restore"
fi

# ── 3. Restore Saved Models ──
log "Restoring saved models..."
MODELS_ARCHIVE=$(find "$EXTRACTED_DIR" -name "saved_models_*.tar.gz" | head -n 1)
if [[ -n "$MODELS_ARCHIVE" ]]; then
    tar xzf "$MODELS_ARCHIVE" -C /tmp/
    rsync -a --delete /tmp/saved_models/ /app/saved_models/ 2>/dev/null || \
    cp -r /tmp/saved_models/* /app/saved_models/ 2>/dev/null || true
    rm -rf /tmp/saved_models
    log "Saved models restore completed"
else
    error "Saved models archive not found — skipping"
fi

# ── 4. Restore Uploads ──
log "Restoring uploads..."
UPLOADS_ARCHIVE=$(find "$EXTRACTED_DIR" -name "uploads_*.tar.gz" | head -n 1)
if [[ -n "$UPLOADS_ARCHIVE" ]]; then
    tar xzf "$UPLOADS_ARCHIVE" -C /tmp/
    rsync -a --delete /tmp/uploads/ /app/backend/uploads/ 2>/dev/null || \
    cp -r /tmp/uploads/* /app/backend/uploads/ 2>/dev/null || true
    rm -rf /tmp/uploads
    log "Uploads restore completed"
else
    error "Uploads archive not found — skipping"
fi

# ── Cleanup ──
rm -rf "$RESTORE_DIR"
log "Restore completed successfully from: $ARCHIVE"
