"""Tests for detection, feedback, and chat routes."""

import io
import base64
from unittest.mock import MagicMock
import pytest
from PIL import Image


class TestModelStatus:
    """GET /api/model-status"""

    def test_model_status(self, client):
        resp = client.get('/api/model-status')
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'model_loaded' in data
        assert 'num_classes' in data
        assert 'timestamp' in data


class TestAnalyze:
    """POST /api/analyze"""

    def test_analyze_no_image(self, client):
        resp = client.post('/api/analyze', json={})
        assert resp.status_code == 400
        data = resp.get_json()
        assert data['success'] is False
        assert 'No image data' in data['message']

    def test_analyze_invalid_image(self, client):
        resp = client.post('/api/analyze', json={
            'image': 'not-valid-base64!!!',
        })
        assert resp.status_code == 400
        data = resp.get_json()
        assert data['success'] is False
        assert 'Invalid image' in data['message']

    def test_analyze_with_mock_prediction(self, client):
        # Create a minimal base64 image
        img = Image.new('RGB', (64, 64), color=(100, 150, 50))
        buf = io.BytesIO()
        img.save(buf, format='PNG')
        b64 = base64.b64encode(buf.getvalue()).decode('ascii')

        resp = client.post('/api/analyze', json={'image': b64})
        # Since model_loader is mocked, it falls back to mock prediction
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['success'] is True
        assert 'disease' in data
        assert 'confidence' in data
        assert 'leaf_check' in data

    def test_analyze_saves_detection_when_authenticated(self, client, auth):
        auth.register('analyzetest', 'analyze@example.com', 'mypass123')
        headers = auth.headers('analyze@example.com', 'mypass123')

        img = Image.new('RGB', (64, 64), color=(100, 150, 50))
        buf = io.BytesIO()
        img.save(buf, format='PNG')
        b64 = base64.b64encode(buf.getvalue()).decode('ascii')

        resp = client.post('/api/analyze', headers=headers, json={'image': b64})
        assert resp.status_code == 200

        # Verify detection was saved
        dresp = client.get('/api/detections', headers=headers)
        assert dresp.status_code == 200
        data = dresp.get_json()
        assert data['count'] >= 1


class TestDetections:
    """GET/DELETE /api/detections"""

    def test_get_detections_requires_auth(self, client):
        resp = client.get('/api/detections')
        assert resp.status_code == 401

    def test_get_detections_empty(self, client, auth):
        auth.register('dettest', 'det@example.com', 'mypass123')
        headers = auth.headers('det@example.com', 'mypass123')
        resp = client.get('/api/detections', headers=headers)
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['success'] is True
        assert data['count'] == 0

    def test_delete_detection(self, client, auth, app):
        from database import save_detection
        auth.register('deltest', 'del@example.com', 'mypass123')
        headers = auth.headers('del@example.com', 'mypass123')

        with app.app_context():
            user = __import__('database').get_user_by_email('del@example.com')
            det = save_detection(user_id=user.id, disease='Rust')
            det_id = det.id

        resp = client.delete(f'/api/detections/{det_id}', headers=headers)
        assert resp.status_code == 200
        assert resp.get_json()['success'] is True

    def test_delete_detection_not_found(self, client, auth):
        auth.register('delnf', 'delnf@example.com', 'mypass123')
        headers = auth.headers('delnf@example.com', 'mypass123')
        resp = client.delete('/api/detections/99999', headers=headers)
        assert resp.status_code == 404


class TestChat:
    """POST /api/chat"""

    def test_chat_response(self, client):
        resp = client.post('/api/chat', json={
            'message': 'How do I prevent bean rust?',
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['success'] is True
        assert 'prevent' in data['message'].lower() or 'rust' in data['message'].lower()

    def test_chat_missing_query(self, client):
        resp = client.post('/api/chat', json={})
        assert resp.status_code == 200  # empty message is handled gracefully
        data = resp.get_json()
        assert data['success'] is True
        assert 'Assistant' in data['message']

    def test_chat_with_last_detection(self, client):
        resp = client.post('/api/chat', json={
            'message': 'What was my last detection?',
            'last_detection': {
                'disease': 'Bean Rust',
                'confidence': 0.87,
                'severity': 'Moderate',
                'is_healthy': False,
            }
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['success'] is True
        assert 'Bean Rust' in data['message']


class TestFeedbackRoute:
    """POST /api/feedback"""

    def test_feedback_no_auth(self, client):
        resp = client.post('/api/feedback', json={
            'predicted_class': 'A',
            'correct_class': 'B',
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['success'] is True
        assert 'feedback_id' in data

    def test_feedback_with_auth(self, client, auth):
        auth.register('fbtest', 'fb@example.com', 'mypass123')
        headers = auth.headers('fb@example.com', 'mypass123')
        resp = client.post('/api/feedback', headers=headers, json={
            'predicted_class': 'Tomato___healthy',
            'correct_class': 'Tomato___Early_blight',
            'confidence': 0.6,
            'image_id': 'img123.jpg',
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['success'] is True

    def test_feedback_defaults(self, client):
        resp = client.post('/api/feedback', json={})
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['success'] is True
        assert data['feedback_id']
