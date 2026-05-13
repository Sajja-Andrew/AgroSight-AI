"""Tests for Flask authentication routes in app.py."""

import pytest


class TestHealthAndHome:
    """Basic route availability."""

    def test_health_check(self, client):
        resp = client.get('/api/health')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['status'] == 'healthy'
        assert 'model_loaded' in data

    def test_home_catalog(self, client):
        resp = client.get('/')
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'endpoints' in data
        assert '/api/analyze' in data['endpoints']


class TestAuthRegister:
    """POST /api/auth/register"""

    def test_register_success(self, client):
        resp = client.post('/api/auth/register', json={
            'username': 'alice',
            'email': 'alice@example.com',
            'password': 'password123',
            'phone': '+256700000001',
            'role': 'farmer',
            'location': 'Kampala',
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['success'] is True
        assert 'token' in data
        assert data['user']['username'] == 'alice'

    def test_register_duplicate(self, client):
        client.post('/api/auth/register', json={
            'username': 'bob',
            'email': 'bob@example.com',
            'password': 'password123',
        })
        resp = client.post('/api/auth/register', json={
            'username': 'bob2',
            'email': 'bob@example.com',
            'password': 'password123',
        })
        assert resp.status_code == 409
        data = resp.get_json()
        assert data['success'] is False
        assert 'already exists' in data['message']

    def test_register_missing_fields(self, client):
        resp = client.post('/api/auth/register', json={
            'username': 'c',
        })
        assert resp.status_code == 400
        data = resp.get_json()
        assert data['success'] is False

    def test_register_invalid_username(self, client):
        resp = client.post('/api/auth/register', json={
            'username': 'ab',  # too short
            'email': 'ab@example.com',
            'password': 'password123',
        })
        assert resp.status_code == 400
        assert 'Username must be' in resp.get_json()['message']

    def test_register_invalid_email(self, client):
        resp = client.post('/api/auth/register', json={
            'username': 'dave',
            'email': 'not-an-email',
            'password': 'password123',
        })
        assert resp.status_code == 400
        assert 'valid email' in resp.get_json()['message']

    def test_register_weak_password(self, client):
        resp = client.post('/api/auth/register', json={
            'username': 'eve',
            'email': 'eve@example.com',
            'password': '123',
        })
        assert resp.status_code == 400
        assert 'at least 8 characters' in resp.get_json()['message']

    def test_register_defaults_role_to_farmer(self, client):
        resp = client.post('/api/auth/register', json={
            'username': 'frank',
            'email': 'frank@example.com',
            'password': 'password123',
            'role': 'invalid_role',
        })
        assert resp.status_code == 200
        assert resp.get_json()['user']['role'] == 'farmer'


class TestAuthLogin:
    """POST /api/auth/login"""

    def test_login_success(self, client, auth):
        auth.register('logintest', 'logintest@example.com', 'mypass123')
        resp = auth.login('logintest@example.com', 'mypass123')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['success'] is True
        assert 'token' in data
        assert data['user']['email'] == 'logintest@example.com'

    def test_login_failure(self, client, auth):
        auth.register('badlogin', 'bad@example.com', 'mypass123')
        resp = client.post('/api/auth/login', json={
            'identifier': 'bad@example.com',
            'password': 'wrongpass',
        })
        assert resp.status_code == 401
        assert resp.get_json()['success'] is False

    def test_login_missing_fields(self, client):
        resp = client.post('/api/auth/login', json={})
        assert resp.status_code == 400


class TestAuthMe:
    """GET /api/auth/me"""

    def test_me_authenticated(self, client, auth):
        auth.register('metest', 'me@example.com', 'mypass123')
        headers = auth.headers('me@example.com', 'mypass123')
        resp = client.get('/api/auth/me', headers=headers)
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['success'] is True
        assert data['user']['email'] == 'me@example.com'

    def test_me_no_token(self, client):
        resp = client.get('/api/auth/me')
        assert resp.status_code == 401

    def test_me_update_profile(self, client, auth):
        auth.register('updatetest', 'update@example.com', 'mypass123')
        headers = auth.headers('update@example.com', 'mypass123')
        resp = client.put('/api/auth/me', headers=headers, json={
            'phone': '+256711111111',
            'location': 'Jinja',
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['user']['phone'] == '+256711111111'
        assert data['user']['location'] == 'Jinja'

    def test_me_update_duplicate_email(self, client, auth):
        auth.register('userone', 'u1@example.com', 'mypass123')
        auth.register('usertwo', 'u2@example.com', 'mypass123')
        headers = auth.headers('u1@example.com', 'mypass123')
        resp = client.put('/api/auth/me', headers=headers, json={
            'email': 'u2@example.com',
        })
        assert resp.status_code == 409


class TestAdminLogin:
    """POST /api/auth/admin/login"""

    def test_admin_login_success(self, client, app):
        from database import create_admin
        with app.app_context():
            create_admin('root', 'root@example.com', 'toor')
        resp = client.post('/api/auth/admin/login', json={
            'identifier': 'root@example.com',
            'password': 'toor',
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['success'] is True
        assert data['user']['role'] == 'admin'

    def test_admin_login_non_admin(self, client, auth):
        auth.register('farmerjoe', 'fj@example.com', 'mypass123', role='farmer')
        resp = client.post('/api/auth/admin/login', json={
            'identifier': 'fj@example.com',
            'password': 'mypass123',
        })
        assert resp.status_code == 403
        assert 'Admin access' in resp.get_json()['message']

    def test_admin_login_wrong_password(self, client, app):
        from database import create_admin
        with app.app_context():
            create_admin('root2', 'r2@example.com', 'toor')
        resp = client.post('/api/auth/admin/login', json={
            'identifier': 'r2@example.com',
            'password': 'wrong',
        })
        assert resp.status_code == 401
