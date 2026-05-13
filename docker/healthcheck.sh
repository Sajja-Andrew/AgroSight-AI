#!/bin/bash
# ═══════════════════════════════════════════════════════════════
# AgroSight AI — Docker Health Check
# ═══════════════════════════════════════════════════════════════
# Called by Docker HEALTHCHECK instruction every 30s.
# Returns 0 if all critical services are healthy.
# ═══════════════════════════════════════════════════════════════

set -euo pipefail

# Check Nginx is responding
if ! curl -fsS http://127.0.0.1:8080/ > /dev/null 2>&1; then
    echo "HEALTHCHECK FAIL: Nginx not responding on port 8080"
    exit 1
fi

# Check Flask API health endpoint
if ! curl -fsS http://127.0.0.1:8080/api/health > /dev/null 2>&1; then
    echo "HEALTHCHECK FAIL: Flask API health check failed"
    exit 1
fi

# Check Socket.IO server (Node.js) via Nginx proxy
# We can't easily test Socket.IO without a client, but we check
# if the node process is running.
if ! pgrep -f "node server.js" > /dev/null 2>&1; then
    echo "HEALTHCHECK FAIL: Node.js chat server not running"
    exit 1
fi

# Optional: Check Supervisor is running
if ! pgrep -x "supervisord" > /dev/null 2>&1; then
    echo "HEALTHCHECK FAIL: Supervisor not running"
    exit 1
fi

echo "HEALTHCHECK OK"
exit 0
