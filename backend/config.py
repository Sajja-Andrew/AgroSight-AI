"""
Smart Crop AI - Centralized Configuration
Loads all settings from environment variables with sensible defaults.
"""

import os
from pathlib import Path

# â”€â”€ BASE PATHS â”€â”€
BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent

# â”€â”€ FLASK â”€â”€
SECRET_KEY = os.environ.get('SECRET_KEY', 'AgroSightAI-dev-secret-change-in-production')
DEBUG = os.environ.get('DEBUG', 'false').lower() in ('true', '1', 'yes')
MAX_CONTENT_LENGTH = int(os.environ.get('MAX_CONTENT_LENGTH', 16 * 1024 * 1024))

# â”€â”€ CORS â”€â”€
# Default to '*' in development so the frontend (Live Server, file://, etc.) can reach the API.
# In production, set CORS_ORIGINS to your frontend domain(s).
_default_cors = os.environ.get('CORS_ORIGINS', '*')
if _default_cors == '*':
    CORS_ORIGINS = '*'
else:
    CORS_ORIGINS = [o.strip() for o in _default_cors.split(',') if o.strip()]

# â”€â”€ JWT â”€â”€
JWT_SECRET_KEY = os.environ.get('JWT_SECRET_KEY', SECRET_KEY)
JWT_ACCESS_TOKEN_EXPIRES_DAYS = int(os.environ.get('JWT_ACCESS_TOKEN_EXPIRES_DAYS', 7))

# â”€â”€ DATABASE â”€â”€
DATABASE_URI = os.environ.get('DATABASE_URL', f'sqlite:///{BASE_DIR / "AgroSightAI.db"}')

# â”€â”€ MODEL PATHS (relative to project root) â”€â”€
MODEL_PATH = os.environ.get('MODEL_PATH', str(PROJECT_ROOT / 'saved_models' / 'best_model.keras'))
CLASS_INDICES_PATH = os.environ.get('CLASS_INDICES_PATH', str(PROJECT_ROOT / 'saved_models' / 'class_indices.json'))
DISEASE_INFO_PATH = os.environ.get('DISEASE_INFO_PATH', str(PROJECT_ROOT / 'saved_models' / 'disease_info.json'))
LEAF_DETECTOR_PATH = os.environ.get('LEAF_DETECTOR_PATH', str(PROJECT_ROOT / 'saved_models' / 'leaf_detector.keras'))
LEAF_DETECTOR_CONFIG = os.environ.get('LEAF_DETECTOR_CONFIG', str(PROJECT_ROOT / 'saved_models' / 'leaf_detector_config.json'))

# â”€â”€ PYTORCH FALLBACK PATHS â”€â”€
PYTORCH_MODEL_DIR = os.environ.get('PYTORCH_MODEL_DIR', str(PROJECT_ROOT / 'saved_models_pytorch'))

# â”€â”€ UPLOADS â”€â”€
UPLOAD_FOLDER = os.environ.get('UPLOAD_FOLDER', str(BASE_DIR / 'uploads'))
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'bmp', 'webp'}
MAX_UPLOAD_SIZE_MB = int(os.environ.get('MAX_UPLOAD_SIZE_MB', 16))

# â”€â”€ RATE LIMITING â”€â”€
RATE_LIMIT_DEFAULT = os.environ.get('RATE_LIMIT_DEFAULT', '200 per day;50 per hour')
RATE_LIMIT_AUTH = os.environ.get('RATE_LIMIT_AUTH', '10 per minute')
RATE_LIMIT_ANALYZE = os.environ.get('RATE_LIMIT_ANALYZE', '30 per minute')

# â”€â”€ LOGGING â”€â”€
LOG_LEVEL = os.environ.get('LOG_LEVEL', 'INFO')

# â”€â”€ SECURITY â”€â”€
ENABLE_SECURE_HEADERS = os.environ.get('ENABLE_SECURE_HEADERS', 'true').lower() in ('true', '1', 'yes')
ENABLE_RATE_LIMITING = os.environ.get('ENABLE_RATE_LIMITING', 'true').lower() in ('true', '1', 'yes')

# ── ADMIN SEED ──
ADMIN_USERNAME = os.environ.get('ADMIN_USERNAME', 'admin')
ADMIN_EMAIL = os.environ.get('ADMIN_EMAIL', 'admin@agrosight.ai')
ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD', 'adminpass123')

# â”€â”€ CHAT AI â”€â”€
ENABLE_AI_CHAT = os.environ.get('ENABLE_AI_CHAT', 'true').lower() in ('true', '1', 'yes')

# â”€â”€ REDIS CACHE â”€â”€
REDIS_URL = os.environ.get('REDIS_URL', 'redis://localhost:6379/0')
REDIS_ENABLED = os.environ.get('REDIS_ENABLED', 'true').lower() in ('true', '1', 'yes')

# â”€â”€ MINIO OBJECT STORAGE â”€â”€
MINIO_ENDPOINT = os.environ.get('MINIO_ENDPOINT', 'http://localhost:9000')
MINIO_ACCESS_KEY = os.environ.get('MINIO_ACCESS_KEY', 'agrosight')
MINIO_SECRET_KEY = os.environ.get('MINIO_SECRET_KEY', 'change-me-in-production')
MINIO_SECURE = os.environ.get('MINIO_SECURE', 'false').lower() in ('true', '1', 'yes')
MINIO_BUCKET_UPLOADS = os.environ.get('MINIO_BUCKET_UPLOADS', 'uploads')
MINIO_BUCKET_MODELS = os.environ.get('MINIO_BUCKET_MODELS', 'models')
MINIO_BUCKET_DATASETS = os.environ.get('MINIO_BUCKET_DATASETS', 'datasets')
MINIO_BUCKET_FEEDBACK = os.environ.get('MINIO_BUCKET_FEEDBACK', 'feedback')
MINIO_ENABLED = os.environ.get('MINIO_ENABLED', 'true').lower() in ('true', '1', 'yes')

# â”€â”€ RETRAINING PIPELINE â”€â”€
RETRAIN_SCHEDULE = os.environ.get('RETRAIN_SCHEDULE', 'weekly')  # weekly | monthly | off
IMPROVEMENT_THRESHOLD = float(os.environ.get('IMPROVEMENT_THRESHOLD', '0.01'))
MIN_FEEDBACK_COUNT = int(os.environ.get('MIN_FEEDBACK_COUNT', '5'))
