"""
WSGI application entry point for Gunicorn.
Imports and returns the Flask app from the backend module.
"""
import sys
import os

# Ensure both /app and /app/backend are in the Python path
# This handles both Docker (where WORKDIR=/app) and local dev
for path in ['/app', '/app/backend', os.path.dirname(os.path.abspath(__file__))]:
    if path not in sys.path:
        sys.path.insert(0, path)

# Set PYTHONPATH environment variable for subprocesses
os.environ.setdefault('PYTHONPATH', '/app:/app/backend')

from backend.app import app

if __name__ == '__main__':
    app.run()