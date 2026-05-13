"""
Pipeline configuration constants.
Loads settings from environment variables with sensible defaults.
"""

import os
from pathlib import Path

# Base paths (relative to backend/)
BACKEND_DIR = Path(__file__).resolve().parent.parent
PROJECT_ROOT = BACKEND_DIR.parent

# ── Feedback Sources ──
FEEDBACK_JSON_PATH = Path(os.environ.get('FEEDBACK_JSON_PATH', str(BACKEND_DIR / 'data' / 'feedback.json')))
FEEDBACK_LOG_PATH = Path(os.environ.get('FEEDBACK_LOG_PATH', str(BACKEND_DIR / 'feedback' / 'feedback_log.json')))
FEEDBACK_IMAGE_DIR = Path(os.environ.get('FEEDBACK_IMAGE_DIR', str(BACKEND_DIR / 'feedback')))

# ── Dataset & Model Paths ──
ORIGINAL_DATA_DIR = Path(os.environ.get('ORIGINAL_DATA_DIR', str(PROJECT_ROOT / 'dataset' / 'processed')))
FEEDBACK_PROCESSED_DIR = Path(os.environ.get('FEEDBACK_PROCESSED_DIR', str(PROJECT_ROOT / 'dataset' / 'feedback_processed')))
MODEL_SAVE_DIR = Path(os.environ.get('MODEL_SAVE_DIR', str(PROJECT_ROOT / 'saved_models')))
CLASS_INDICES_PATH = Path(os.environ.get('CLASS_INDICES_PATH', str(PROJECT_ROOT / 'saved_models' / 'class_indices.json')))

# ── Champion Model Paths ──
CHAMPION_MODEL_PATH = Path(os.environ.get('CHAMPION_MODEL_PATH', str(MODEL_SAVE_DIR / 'best_model_finetuned.keras')))
FALLBACK_MODEL_PATH = Path(os.environ.get('FALLBACK_MODEL_PATH', str(MODEL_SAVE_DIR / 'best_model.keras')))

# ── Registry & Logs ──
MODEL_REGISTRY_PATH = Path(os.environ.get('MODEL_REGISTRY_PATH', str(MODEL_SAVE_DIR / 'model_registry.json')))
RETRAIN_LOG_DIR = Path(os.environ.get('RETRAIN_LOG_DIR', str(MODEL_SAVE_DIR / 'retrain_logs')))
PIPELINE_LOCK_FILE = Path(os.environ.get('PIPELINE_LOCK_FILE', str(MODEL_SAVE_DIR / '.pipeline_running')))

# ── Validation Thresholds ──
MIN_FEEDBACK_COUNT = int(os.environ.get('MIN_FEEDBACK_COUNT', '5'))
MIN_CONFIDENCE = float(os.environ.get('MIN_CONFIDENCE', '0.0'))
IMPROVEMENT_THRESHOLD = float(os.environ.get('IMPROVEMENT_THRESHOLD', '0.01'))  # 1% min improvement

# ── Training Hyperparameters ──
DEFAULT_EPOCHS = int(os.environ.get('DEFAULT_EPOCHS', '10'))
DEFAULT_BATCH_SIZE = int(os.environ.get('DEFAULT_BATCH_SIZE', '16'))
DEFAULT_LEARNING_RATE = float(os.environ.get('DEFAULT_LEARNING_RATE', '1e-5'))
DEFAULT_FINE_TUNE_LAYERS = int(os.environ.get('DEFAULT_FINE_TUNE_LAYERS', '20'))
TRAIN_SPLIT = float(os.environ.get('TRAIN_SPLIT', '0.8'))
RANDOM_SEED = int(os.environ.get('RANDOM_SEED', '42'))

# ── Scheduling ──
RETRAIN_SCHEDULE = os.environ.get('RETRAIN_SCHEDULE', 'weekly')  # weekly | monthly | off
RETRAIN_DAY_OF_WEEK = int(os.environ.get('RETRAIN_DAY_OF_WEEK', '0'))  # Sunday
RETRAIN_HOUR = int(os.environ.get('RETRAIN_HOUR', '2'))
RETRAIN_MINUTE = int(os.environ.get('RETRAIN_MINUTE', '0'))

# ── Deployment ──
KEEP_VERSIONS = int(os.environ.get('KEEP_VERSIONS', '3'))
MODEL_FORMAT = os.environ.get('MODEL_FORMAT', 'keras')  # keras | savedmodel | both

# ── Logging ──
LOG_LEVEL = os.environ.get('LOG_LEVEL', 'INFO')
