#!/bin/bash
# Start gunicorn with correct Python path
export PYTHONPATH=/app:/app/backend:$PYTHONPATH
cd /app
exec gunicorn --bind 0.0.0.0:5000 --workers 2 --threads 4 --timeout 60 --keep-alive 2 --worker-tmp-dir /tmp/agrosight --preload wsgi:app
