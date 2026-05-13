"""
Shared pytest fixtures for the Smart Crop AI backend.

Patches TensorFlow model loading before app import to avoid heavy
Keras loads during test discovery. Creates a fresh Flask app per test
so SQLAlchemy can be initialized cleanly each time.
"""

import os
import sys
import base64
import io
import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from flask import Flask
from flask_jwt_extended import JWTManager
from PIL import Image

# ── Stub TensorFlow and Keras before any pipeline modules import them ──
# pipeline.preprocessing imports tensorflow.keras.preprocessing.image at module level.
# We create a deep mock tree so no real TF import is needed.
_tf_mock = MagicMock()
_tf_mock.keras.models.load_model.return_value = MagicMock()
_tf_mock.keras.preprocessing.image.ImageDataGenerator.return_value = MagicMock()
_tf_mock.config.experimental.set_memory_growth = MagicMock()
_tf_mock.__version__ = '2.16.1'

# Register all the submodules that might be imported
for _mod_name in [
    'tensorflow', 'tensorflow.keras', 'tensorflow.keras.models',
    'tensorflow.keras.preprocessing', 'tensorflow.keras.preprocessing.image',
    'tensorflow.keras.callbacks', 'tensorflow.keras.optimizers',
    'tensorflow.keras.applications', 'tensorflow.keras.layers',
]:
    sys.modules[_mod_name] = _tf_mock

# Provide named fake classes for Keras callbacks so tests can assert on type names
class ModelCheckpoint:
    def __init__(self, **kwargs):
        self.kwargs = kwargs
class EarlyStopping:
    def __init__(self, **kwargs):
        self.kwargs = kwargs
class ReduceLROnPlateau:
    def __init__(self, **kwargs):
        self.kwargs = kwargs

_tf_mock.ModelCheckpoint = ModelCheckpoint
_tf_mock.EarlyStopping = EarlyStopping
_tf_mock.ReduceLROnPlateau = ReduceLROnPlateau
_tf_mock.keras.callbacks.ModelCheckpoint = ModelCheckpoint
_tf_mock.keras.callbacks.EarlyStopping = EarlyStopping
_tf_mock.keras.callbacks.ReduceLROnPlateau = ReduceLROnPlateau

# Provide a fake Adam optimizer
class Adam:
    def __init__(self, **kwargs):
        self.kwargs = kwargs
_tf_mock.keras.optimizers.Adam = Adam

# Provide fake applications
class MobileNetV2:
    pass
_tf_mock.keras.applications.MobileNetV2 = MobileNetV2

# ── Import modules but let app.py register its routes on a dummy app ──
# We import app.py once to get all route functions and blueprints.
# app.py will call init_db() and load_models() at import time,
# but on a throwaway app instance that we never use in tests.
import database as _db_module

# Temporarily redirect init_app so the production DB isn't touched
_original_database_init_app = _db_module.init_app
_db_module.init_app = lambda app: None

# Import app.py for its route functions/blueprints
import app as _app_module

# Restore init_app so our fixture can use it
_db_module.init_app = _original_database_init_app


def _copy_routes(src_app: Flask, dst_app: Flask):
    """Copy URL rules and view functions from src_app to dst_app."""
    for rule in src_app.url_map.iter_rules():
        if rule.endpoint == 'static':
            continue
        view_func = src_app.view_functions.get(rule.endpoint)
        if view_func is None:
            continue
        # Avoid re-registering if the endpoint already exists
        if rule.endpoint in dst_app.view_functions:
            continue
        dst_app.add_url_rule(
            rule.rule,
            endpoint=rule.endpoint,
            view_func=view_func,
            methods=rule.methods - {'HEAD', 'OPTIONS'},
        )


@pytest.fixture
def app():
    """Create a fresh Flask app for testing with copied routes."""
    db_fd, db_path = tempfile.mkstemp(suffix='.db')

    test_config = {
        'TESTING': True,
        'SQLALCHEMY_DATABASE_URI': f'sqlite:///{db_path}',
        'SQLALCHEMY_TRACK_MODIFICATIONS': False,
        'JWT_SECRET_KEY': 'test-secret-key',
        'JWT_ACCESS_TOKEN_EXPIRES': False,
        'ENABLE_RATE_LIMITING': False,
        'ENABLE_SECURE_HEADERS': False,
        'WTF_CSRF_ENABLED': False,
        'MAX_CONTENT_LENGTH': 16 * 1024 * 1024,
        'UPLOAD_FOLDER': tempfile.mkdtemp(),
    }

    fresh_app = Flask(__name__)
    fresh_app.config.update(test_config)

    # Copy routes from the imported app module
    _copy_routes(_app_module.app, fresh_app)

    # Register blueprints that may have been added separately
    for bp_name, bp in _app_module.app.blueprints.items():
        if bp_name not in fresh_app.blueprints:
            fresh_app.register_blueprint(bp)

    # Apply after_request handlers (secure headers, etc.)
    for handler in _app_module.app.after_request_funcs.get(None, []):
        fresh_app.after_request(handler)

    # Initialize JWTManager and SQLAlchemy with the fresh app
    JWTManager(fresh_app)
    _db_module.db.init_app(fresh_app)

    with fresh_app.app_context():
        _db_module.db.create_all()
        yield fresh_app
        _db_module.db.drop_all()

    # Ensure engine connections are closed before deleting the temp DB on Windows
    with fresh_app.app_context():
        _db_module.db.engine.dispose()
    os.close(db_fd)
    try:
        os.unlink(db_path)
    except PermissionError:
        pass  # Windows may hold the file briefly; temp cleaner will handle it


@pytest.fixture
def client(app):
    """A Flask test client."""
    return app.test_client()


@pytest.fixture
def db_session(app):
    """Provide a database session that rolls back after the test."""
    with app.app_context():
        connection = _db_module.db.engine.connect()
        transaction = connection.begin()
        session = _db_module.db.session

        yield session

        transaction.rollback()
        connection.close()
        session.remove()


@pytest.fixture
def sample_image():
    """Return a simple RGB PIL Image."""
    return Image.new('RGB', (224, 224), color=(120, 180, 90))


@pytest.fixture
def sample_image_b64(sample_image):
    """Return a base64-encoded PNG of the sample image."""
    buf = io.BytesIO()
    sample_image.save(buf, format='PNG')
    return base64.b64encode(buf.getvalue()).decode('ascii')


@pytest.fixture
def mock_class_indices():
    """Return a small class-indices dict for model tests."""
    return {
        'Tomato___healthy': 0,
        'Potato___Late_blight': 1,
        'Bean___rust': 2,
    }


@pytest.fixture
def mock_disease_info():
    """Return minimal disease info entries."""
    return {
        'Tomato___healthy': {
            'name': 'Tomato - Healthy',
            'symptoms': 'No symptoms. Plant is healthy.',
            'solution': 'No treatment needed.',
            'prevention': 'Maintain good practices.',
            'severity': 'None',
        },
        'Potato___Late_blight': {
            'name': 'Potato - Late Blight',
            'symptoms': 'Dark spots on leaves and stems.',
            'solution': 'Apply fungicide. Remove infected plants.',
            'prevention': 'Ensure good drainage. Crop rotation.',
            'severity': 'High',
        },
        'Bean___rust': {
            'name': 'Bean - Rust',
            'symptoms': 'Reddish-brown pustules.',
            'solution': 'Apply fungicide.',
            'prevention': 'Resistant varieties.',
            'severity': 'Moderate',
        },
    }


class AuthHelper:
    """Helper to create authenticated requests in tests."""
    def __init__(self, client, app):
        self.client = client
        self.app = app

    def register(self, username='testuser', email='test@example.com',
                 password='testpass123', phone='+256700000001',
                 role='farmer', location='Kampala'):
        resp = self.client.post('/api/auth/register', json={
            'username': username,
            'email': email,
            'password': password,
            'phone': phone,
            'role': role,
            'location': location,
        })
        return resp

    def login(self, identifier='test@example.com', password='testpass123'):
        resp = self.client.post('/api/auth/login', json={
            'identifier': identifier,
            'password': password,
        })
        return resp

    def headers(self, identifier='test@example.com', password='testpass123'):
        resp = self.login(identifier, password)
        data = resp.get_json()
        token = data.get('token') or data.get('access_token')
        return {'Authorization': f'Bearer {token}'}

    def admin_headers(self):
        from database import create_admin
        with self.app.app_context():
            create_admin('adminuser', 'admin@test.com', 'adminpass123')
        return self.headers('admin@test.com', 'adminpass123')


@pytest.fixture
def auth(client, app):
    """Return an AuthHelper for the current client."""
    return AuthHelper(client, app)


@pytest.fixture
def tmp_path_feedback(tmp_path):
    """Provide a temp directory with mock feedback.json and feedback_log.json."""
    feedback_file = tmp_path / 'feedback.json'
    feedback_log = tmp_path / 'feedback_log.json'
    feedback_file.write_text(json.dumps({
        'entries': [
            {'id': '1', 'correct_class': 'A', 'timestamp': '2024-01-01', 'source': 'user_feedback', 'status': 'verified'},
        ]
    }))
    feedback_log.write_text(json.dumps({
        'entries': [
            {'id': '2', 'correct_class': 'B', 'timestamp': '2024-01-02', 'source': 'user_feedback', 'status': 'verified'},
        ]
    }))
    return tmp_path
