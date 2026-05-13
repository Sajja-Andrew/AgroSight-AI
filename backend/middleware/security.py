"""
Smart Crop AI - Security Middleware
Rate limiting, secure headers, CORS, input validation.
"""

from functools import wraps
from flask import request, jsonify, current_app
import re

# ── RATE LIMITING (simple in-memory) ──
from collections import defaultdict
import time

class SimpleRateLimiter:
    """In-memory per-IP rate limiter. Suitable for single-instance deployments.
    For multi-instance, replace with Redis-backed Flask-Limiter."""
    def __init__(self):
        self.requests = defaultdict(list)

    def is_allowed(self, key, limit, window_seconds):
        now = time.time()
        self.requests[key] = [t for t in self.requests[key] if now - t < window_seconds]
        if len(self.requests[key]) >= limit:
            return False
        self.requests[key].append(now)
        return True

_limiter = SimpleRateLimiter()

def rate_limit(limit=30, window_seconds=60, key_func=None):
    """Decorator to apply rate limiting to a route."""
    def decorator(f):
        @wraps(f)
        def wrapped(*args, **kwargs):
            if not current_app.config.get('ENABLE_RATE_LIMITING', True):
                return f(*args, **kwargs)
            key = key_func() if key_func else request.remote_addr
            if not _limiter.is_allowed(key, limit, window_seconds):
                return jsonify({'success': False, 'message': 'Rate limit exceeded. Please slow down.'}), 429
            return f(*args, **kwargs)
        return wrapped
    return decorator


# ── SECURE HEADS ──
def apply_secure_headers(response):
    """Add security headers to every response."""
    if not current_app.config.get('ENABLE_SECURE_HEADERS', True):
        return response
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
    response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; font-src 'self'; connect-src 'self';"
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    response.headers['Permissions-Policy'] = 'geolocation=(), microphone=(), camera=()'
    return response


# ── INPUT VALIDATION ──
EMAIL_REGEX = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")
PHONE_REGEX = re.compile(r"^[+]?[0-9\s\-()]{7,20}$")
USERNAME_REGEX = re.compile(r"^[a-zA-Z0-9_]{3,30}$")

def validate_email(email):
    return bool(email) and bool(EMAIL_REGEX.match(email))

def validate_phone(phone):
    return bool(phone) and bool(PHONE_REGEX.match(phone))

def validate_username(username):
    return bool(username) and bool(USERNAME_REGEX.match(username))

def sanitize_string(value, max_length=500):
    if not isinstance(value, str):
        return ''
    value = value.strip()
    if len(value) > max_length:
        value = value[:max_length]
    # Remove null bytes and control chars except newline/tab
    value = value.replace('\x00', '')
    value = re.sub(r'[\x00-\x08\x0b-\x0c\x0e-\x1f]', '', value)
    return value

def allowed_file(filename, allowed_extensions=None):
    ext = allowed_extensions or current_app.config.get('ALLOWED_EXTENSIONS', {'png', 'jpg', 'jpeg', 'gif', 'bmp', 'webp'})
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ext
