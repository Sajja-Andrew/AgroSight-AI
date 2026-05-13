"""
WSGI application entry point for Gunicorn.
Imports and returns the Flask app from the backend module.
"""
import sys
import os

# Ensure /app/backend is in the Python path
app_backend = '/app/backend'
if app_backend not in sys.path:
    sys.path.insert(0, app_backend)

# Now import the app
from app import app

if __name__ == '__main__':
    app.run()
