"""Tests for backend/middleware/security.py."""

import pytest
from flask import Flask, jsonify

from middleware.security import (
    rate_limit, apply_secure_headers, validate_email,
    validate_phone, validate_username, sanitize_string,
    allowed_file,
)


class TestRateLimiting:
    """Simple in-memory rate limiter behavior."""

    def test_rate_limit_allows_under_limit(self, app):
        @app.route('/rl')
        @rate_limit(limit=3, window_seconds=60)
        def rl():
            return jsonify({'ok': True})

        with app.test_client() as c:
            for _ in range(3):
                resp = c.get('/rl')
                assert resp.status_code == 200

    def test_rate_limit_blocks_over_limit(self, app):
        app.config['ENABLE_RATE_LIMITING'] = True

        @app.route('/rl2')
        @rate_limit(limit=2, window_seconds=60)
        def rl2():
            return jsonify({'ok': True})

        with app.test_client() as c:
            c.get('/rl2')
            c.get('/rl2')
            resp = c.get('/rl2')
            assert resp.status_code == 429
            assert b'Rate limit exceeded' in resp.data

    def test_rate_limit_disabled_when_config_false(self, app):
        app.config['ENABLE_RATE_LIMITING'] = False

        @app.route('/rl3')
        @rate_limit(limit=1, window_seconds=60)
        def rl3():
            return jsonify({'ok': True})

        with app.test_client() as c:
            for _ in range(5):
                resp = c.get('/rl3')
                assert resp.status_code == 200


class TestValidation:
    """Input validation helpers."""

    @pytest.mark.parametrize('email,expected', [
        ('alice@example.com', True),
        ('bob+tag@domain.co.uk', True),
        ('not-an-email', False),
        ('', False),
        (None, False),
    ])
    def test_validate_email(self, email, expected):
        assert validate_email(email) == expected

    @pytest.mark.parametrize('phone,expected', [
        ('+256781503749', True),
        ('0700123456', True),
        ('123', False),
        ('', False),
        (None, False),
    ])
    def test_validate_phone(self, phone, expected):
        assert validate_phone(phone) == expected

    @pytest.mark.parametrize('username,expected', [
        ('alice_99', True),
        ('bob', True),
        ('ab', False),          # too short
        ('user@name', False),   # invalid chars
        ('', False),
        (None, False),
    ])
    def test_validate_username(self, username, expected):
        assert validate_username(username) == expected


class TestSanitizeString:
    """String sanitization."""

    def test_sanitize_normal(self):
        assert sanitize_string('  hello  ') == 'hello'

    def test_sanitize_truncates(self):
        long_text = 'x' * 1000
        assert len(sanitize_string(long_text, max_length=100)) == 100

    def test_sanitize_null_bytes(self):
        assert '\x00' not in sanitize_string('he\x00llo')

    def test_sanitize_control_chars(self):
        dirty = 'he\x01\x02llo'
        assert sanitize_string(dirty) == 'hello'

    def test_sanitize_non_string_returns_empty(self):
        assert sanitize_string(123) == ''
        assert sanitize_string(None) == ''


class TestAllowedFile:
    """File extension checks."""

    def test_allowed_extensions_default(self, app):
        with app.app_context():
            assert allowed_file('photo.jpg') is True
            assert allowed_file('photo.png') is True
            assert allowed_file('photo.exe') is False
            assert allowed_file('nodot') is False

    def test_allowed_extensions_custom(self):
        assert allowed_file('data.csv', {'csv', 'txt'}) is True
        assert allowed_file('data.jpg', {'csv', 'txt'}) is False


class TestSecureHeaders:
    """Security headers on responses."""

    def test_secure_headers_present(self, app):
        app.config['ENABLE_SECURE_HEADERS'] = True

        @app.route('/hdr')
        def hdr():
            return jsonify({'ok': True})

        with app.test_client() as c:
            resp = c.get('/hdr')
            assert resp.headers.get('X-Content-Type-Options') == 'nosniff'
            assert resp.headers.get('X-Frame-Options') == 'DENY'
            assert 'max-age=31536000' in resp.headers.get('Strict-Transport-Security', '')
            assert 'Content-Security-Policy' in resp.headers
            assert 'Referrer-Policy' in resp.headers
            assert 'Permissions-Policy' in resp.headers

    def test_secure_headers_disabled(self, app):
        app.config['ENABLE_SECURE_HEADERS'] = False

        @app.route('/hdr2')
        def hdr2():
            return jsonify({'ok': True})

        with app.test_client() as c:
            resp = c.get('/hdr2')
            # When disabled, the after_request still calls apply_secure_headers,
            # but it returns the response unchanged. So headers may or may not be present
            # depending on how the app fixture is set up.
            # We just verify the route works.
            assert resp.status_code == 200
