"""Tests for pipeline/training.py FeedbackRetrainer."""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

from pipeline.training import FeedbackRetrainer


class TestLoadChampion:
    """Champion model loading."""

    def test_loads_existing_champion(self, tmp_path):
        champion = tmp_path / 'best_model_finetuned.keras'
        champion.write_bytes(b'fake')

        with patch('pipeline.training.tf') as mock_tf:
            mock_model = MagicMock()
            mock_tf.keras.models.load_model.return_value = mock_model
            trainer = FeedbackRetrainer()
            model = trainer._load_champion(champion)
            assert model is mock_model
            mock_tf.keras.models.load_model.assert_called_once_with(str(champion))

    def test_falls_back_when_champion_missing(self, tmp_path, monkeypatch):
        fallback = tmp_path / 'best_model.keras'
        fallback.write_bytes(b'fake')
        monkeypatch.setattr('pipeline.training.config.FALLBACK_MODEL_PATH', fallback)
        monkeypatch.setattr('pipeline.training.config.CHAMPION_MODEL_PATH', tmp_path / 'missing.keras')

        with patch('pipeline.training.tf') as mock_tf:
            mock_model = MagicMock()
            mock_tf.keras.models.load_model.return_value = mock_model
            trainer = FeedbackRetrainer()
            model = trainer._load_champion()
            assert model is mock_model

    def test_raises_when_no_model_found(self, tmp_path, monkeypatch):
        monkeypatch.setattr('pipeline.training.config.CHAMPION_MODEL_PATH', tmp_path / 'missing.keras')
        monkeypatch.setattr('pipeline.training.config.FALLBACK_MODEL_PATH', tmp_path / 'also_missing.keras')

        trainer = FeedbackRetrainer()
        with pytest.raises(FileNotFoundError):
            trainer._load_champion()


class TestSetupIncremental:
    """Incremental training setup."""

    def test_unfreezes_and_recompiles(self):
        mock_model = MagicMock()
        mock_model.layers = []
        trainer = FeedbackRetrainer()
        trainer.model = mock_model
        with patch('pipeline.training.tf') as mock_tf:
            trainer._setup_incremental_training()
            assert mock_model.trainable is True
            mock_model.compile.assert_called_once()
            args = mock_model.compile.call_args[1]
            assert args['loss'] == 'categorical_crossentropy'
            assert 'accuracy' in args['metrics']


class TestBuildCallbacks:
    """Callback construction."""

    def test_returns_three_callbacks(self, tmp_path):
        trainer = FeedbackRetrainer(model_save_dir=tmp_path)
        cbs = trainer._build_callbacks()
        assert len(cbs) == 3
        names = [type(cb).__name__ for cb in cbs]
        assert 'ModelCheckpoint' in names
        assert 'EarlyStopping' in names
        assert 'ReduceLROnPlateau' in names


class TestRetrain:
    """End-to-end retrain orchestration."""

    def test_incremental_mode(self, tmp_path):
        champion = tmp_path / 'champion.keras'
        champion.write_bytes(b'fake')

        mock_train_data = MagicMock()
        mock_train_data.class_indices = {'A': 0, 'B': 1}
        mock_val_data = MagicMock()

        with patch('pipeline.training.tf') as mock_tf:
            mock_model = MagicMock()
            mock_model.layers = []
            mock_history = MagicMock()
            mock_history.history = {
                'loss': [0.5, 0.4],
                'accuracy': [0.8, 0.9],
                'val_loss': [0.6, 0.5],
                'val_accuracy': [0.7, 0.85],
            }
            mock_model.fit.return_value = mock_history
            mock_tf.keras.models.load_model.return_value = mock_model

            trainer = FeedbackRetrainer(model_save_dir=tmp_path, epochs=2)
            result = trainer.retrain(mock_train_data, mock_val_data, mode='incremental',
                                      base_model_path=champion)

            assert result['mode'] == 'incremental'
            assert result['epochs_trained'] == 2
            assert 'model_path' in result
            assert 'history' in result

    def test_full_mode_builds_new_model(self, tmp_path):
        mock_train_data = MagicMock()
        mock_train_data.class_indices = {'A': 0, 'B': 1}
        mock_val_data = MagicMock()

        with patch('pipeline.training.tf') as mock_tf, \
             patch('model.model.CropDiseaseModel') as MockCropModel:
            mock_crop = MagicMock()
            mock_model = MagicMock()
            mock_crop.build_transfer_learning_model.return_value = None
            mock_crop.compile_model.return_value = None
            mock_crop.model = mock_model
            MockCropModel.return_value = mock_crop

            mock_history = MagicMock()
            mock_history.history = {
                'loss': [0.5],
                'accuracy': [0.8],
                'val_loss': [0.6],
                'val_accuracy': [0.7],
            }
            mock_model.fit.return_value = mock_history

            trainer = FeedbackRetrainer(model_save_dir=tmp_path, epochs=1)
            result = trainer.retrain(mock_train_data, mock_val_data, mode='full')

            assert result['mode'] == 'full'
            MockCropModel.assert_called_once()
            mock_crop.build_transfer_learning_model.assert_called_once_with('MobileNetV2')

    def test_unknown_mode_raises(self, tmp_path):
        trainer = FeedbackRetrainer(model_save_dir=tmp_path)
        with pytest.raises(ValueError, match='Unknown mode'):
            trainer.retrain(None, None, mode='invalid')
