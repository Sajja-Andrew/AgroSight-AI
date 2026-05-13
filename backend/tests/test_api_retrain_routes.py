"""Tests for backend/api_retrain_routes.py admin endpoints."""

import json
from unittest.mock import patch, MagicMock
import pytest


class TestRetrainUnauthorized:
    """Non-admin users cannot trigger retraining."""

    def test_retrain_returns_403_for_farmer(self, client, auth):
        auth.register('farmer', 'farmer@example.com', 'mypass123', role='farmer')
        headers = auth.headers('farmer@example.com', 'mypass123')
        resp = client.post('/api/admin/retrain', headers=headers)
        assert resp.status_code == 403
        data = resp.get_json()
        assert data['success'] is False
        assert 'Admin access' in data['message']

    def test_retrain_status_returns_403_for_farmer(self, client, auth):
        auth.register('farmer2', 'farmer2@example.com', 'mypass123', role='farmer')
        headers = auth.headers('farmer2@example.com', 'mypass123')
        resp = client.get('/api/admin/retrain/status', headers=headers)
        assert resp.status_code == 403

    def test_rollback_returns_403_for_farmer(self, client, auth):
        auth.register('farmer3', 'farmer3@example.com', 'mypass123', role='farmer')
        headers = auth.headers('farmer3@example.com', 'mypass123')
        resp = client.post('/api/admin/retrain/rollback', headers=headers)
        assert resp.status_code == 403


class TestRetrainAdmin:
    """Admin can trigger retraining."""

    def test_retrain_admin_success(self, client, auth, app):
        headers = auth.admin_headers()

        with patch('api_retrain_routes.run_pipeline') as mock_run:
            mock_run.return_value = {
                'success': True,
                'deployed': True,
                'run_id': 'v_test',
                'evaluation': {'accuracy': 0.95},
                'training': {'epochs': 5, 'history': []},
            }
            resp = client.post('/api/admin/retrain', headers=headers, json={
                'mode': 'incremental',
                'dry_run': True,
            })
            assert resp.status_code == 200
            data = resp.get_json()
            assert data['success'] is True
            assert data['deployed'] is True
            assert data['run_id'] == 'v_test'
            # history should be stripped
            assert 'history' not in data['training']

    def test_retrain_admin_failure(self, client, auth, app):
        headers = auth.admin_headers()

        with patch('api_retrain_routes.run_pipeline') as mock_run:
            mock_run.side_effect = RuntimeError('GPU not available')
            resp = client.post('/api/admin/retrain', headers=headers, json={})
            assert resp.status_code == 500
            data = resp.get_json()
            assert data['success'] is False
            assert 'GPU not available' in data['error']


class TestRetrainStatus:
    """GET /api/admin/retrain/status"""

    def test_status_returns_registry(self, client, auth, app, tmp_path):
        headers = auth.admin_headers()

        # Mock registry and log directory
        with patch('api_retrain_routes.ModelRegistry') as MockReg:
            inst = MagicMock()
            inst.get_champion.return_value = {'version_id': 'v1', 'status': 'champion'}
            inst.list_versions.return_value = [
                {'version_id': 'v1', 'status': 'champion', 'created_at': '2024-01-01'},
            ]
            MockReg.return_value = inst

            with patch('api_retrain_routes.config') as mock_cfg:
                mock_cfg.RETRAIN_LOG_DIR = str(tmp_path)
                resp = client.get('/api/admin/retrain/status', headers=headers)
                assert resp.status_code == 200
                data = resp.get_json()
                assert data['success'] is True
                assert data['champion']['version_id'] == 'v1'
                assert data['total_versions'] == 1


class TestRollback:
    """POST /api/admin/retrain/rollback"""

    def test_rollback_success(self, client, auth, app):
        headers = auth.admin_headers()

        with patch('api_retrain_routes.rollback') as mock_rollback:
            mock_rollback.return_value = True
            resp = client.post('/api/admin/retrain/rollback', headers=headers)
            assert resp.status_code == 200
            data = resp.get_json()
            assert data['success'] is True
            assert 'Rolled back' in data['message']

    def test_rollback_failure(self, client, auth, app):
        headers = auth.admin_headers()

        with patch('api_retrain_routes.rollback') as mock_rollback:
            mock_rollback.return_value = False
            resp = client.post('/api/admin/retrain/rollback', headers=headers)
            assert resp.status_code == 500
            data = resp.get_json()
            assert data['success'] is False
            assert 'Rollback failed' in data['message']
