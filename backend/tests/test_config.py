"""Tests for backend/config.py environment loading."""

import os
import pytest

import config as app_config


class TestConfigDefaults:
    """Verify config.py default values when env vars are absent."""

    def test_base_dir_is_path(self):
        assert hasattr(app_config, 'BASE_DIR')
        assert hasattr(app_config.BASE_DIR, 'resolve')

    def test_database_uri_fallback_sqlite(self):
        # When DATABASE_URL is not set, should fallback to SQLite
        assert 'sqlite:///' in app_config.DATABASE_URI

    def test_cors_origins_list_when_comma_separated(self, monkeypatch):
        monkeypatch.setenv('CORS_ORIGINS', 'http://a.com, http://b.com')
        # Re-import to pick up env change
        import importlib
        import config
        importlib.reload(config)
        assert isinstance(config.CORS_ORIGINS, list)
        assert config.CORS_ORIGINS == ['http://a.com', 'http://b.com']

    def test_cors_origins_star_when_explicit(self, monkeypatch):
        monkeypatch.setenv('CORS_ORIGINS', '*')
        import importlib
        import config
        importlib.reload(config)
        assert config.CORS_ORIGINS == '*'

    def test_boolean_env_vars(self, monkeypatch):
        for val in ('true', '1', 'yes'):
            monkeypatch.setenv('DEBUG', val)
            import importlib
            import config
            importlib.reload(config)
            assert config.DEBUG is True

        for val in ('false', '0', 'no', ''):
            monkeypatch.setenv('DEBUG', val)
            importlib.reload(config)
            assert config.DEBUG is False

    def test_secret_key_exists(self):
        assert app_config.SECRET_KEY
        assert app_config.JWT_SECRET_KEY

    def test_model_paths_are_strings(self):
        assert isinstance(app_config.MODEL_PATH, str)
        assert isinstance(app_config.CLASS_INDICES_PATH, str)
        assert isinstance(app_config.DISEASE_INFO_PATH, str)
        assert isinstance(app_config.LEAF_DETECTOR_PATH, str)

    def test_rate_limit_strings_present(self):
        assert 'per day' in app_config.RATE_LIMIT_DEFAULT
        assert 'per minute' in app_config.RATE_LIMIT_AUTH
        assert 'per minute' in app_config.RATE_LIMIT_ANALYZE

    def test_retrain_config_values(self):
        assert app_config.RETRAIN_SCHEDULE in ('weekly', 'monthly', 'off')
        assert 0.0 < app_config.IMPROVEMENT_THRESHOLD < 1.0
        assert isinstance(app_config.MIN_FEEDBACK_COUNT, int)
