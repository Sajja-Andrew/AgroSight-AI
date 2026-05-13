"""Tests for backend/model_loader.py DiseasePredictor logic."""

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch, mock_open
import pytest
import numpy as np

from model_loader import DiseasePredictor, load_models


class TestExtractCrop:
    """Static helper _extract_crop."""

    def test_three_underscores(self):
        assert DiseasePredictor._extract_crop('Tomato___Early_blight') == 'Tomato'

    def test_single_underscore(self):
        assert DiseasePredictor._extract_crop('Potato_Late_blight') == 'Potato'

    def test_no_underscore(self):
        assert DiseasePredictor._extract_crop('Healthy') == 'Unknown Crop'


class TestResolveSeverity:
    """Static helper _resolve_severity."""

    def test_healthy_returns_none(self):
        assert DiseasePredictor._resolve_severity('Unknown', 0.5, True) == 'None'

    def test_db_severity_high(self):
        assert DiseasePredictor._resolve_severity('High', 0.5, False) == 'Severe'
        assert DiseasePredictor._resolve_severity('Severe', 0.5, False) == 'Severe'

    def test_db_severity_medium(self):
        assert DiseasePredictor._resolve_severity('Medium', 0.5, False) == 'Moderate'
        assert DiseasePredictor._resolve_severity('Moderate', 0.5, False) == 'Moderate'

    def test_db_severity_low(self):
        assert DiseasePredictor._resolve_severity('Low', 0.5, False) == 'Mild'
        assert DiseasePredictor._resolve_severity('Mild', 0.5, False) == 'Mild'

    def test_confidence_based_severe(self):
        assert DiseasePredictor._resolve_severity('', 0.95, False) == 'Severe'

    def test_confidence_based_moderate(self):
        assert DiseasePredictor._resolve_severity('', 0.60, False) == 'Moderate'

    def test_confidence_based_mild(self):
        assert DiseasePredictor._resolve_severity('', 0.30, False) == 'Mild'


class TestSplitToList:
    """Static helper _split_to_list."""

    def test_splits_on_semicolon(self):
        assert DiseasePredictor._split_to_list('Apple;Banana;Cherry') == ['Apple', 'Banana', 'Cherry']

    def test_splits_on_period(self):
        assert DiseasePredictor._split_to_list('Apple. Banana. Cherry') == ['Apple', 'Banana', 'Cherry']

    def test_filters_short_parts(self):
        assert DiseasePredictor._split_to_list('Apple. x. Cherry') == ['Apple', 'Cherry']

    def test_empty_returns_empty(self):
        assert DiseasePredictor._split_to_list('') == []
        assert DiseasePredictor._split_to_list(None) == []

    def test_no_split_returns_original(self):
        text = 'Just one sentence here'
        assert DiseasePredictor._split_to_list(text) == [text]


class TestGenerateCauses:
    """Static helper _generate_causes."""

    def test_bacterial(self):
        cause = DiseasePredictor._generate_causes('X', {'name': 'Bacterial spot'})
        assert 'bacteria' in cause.lower()

    def test_fungal(self):
        cause = DiseasePredictor._generate_causes('X', {'name': 'Powdery mildew'})
        assert 'fungal' in cause.lower()

    def test_viral(self):
        cause = DiseasePredictor._generate_causes('X', {'name': 'Mosaic virus'})
        assert 'viral' in cause.lower()

    def test_healthy(self):
        cause = DiseasePredictor._generate_causes('X', {'name': 'Tomato healthy'})
        assert 'good health' in cause.lower()

    def test_existing_causes_preserved(self):
        existing = 'Known cause from database.'
        cause = DiseasePredictor._generate_causes('X', {'name': 'Something', 'causes': existing})
        assert cause == existing.strip()

    def test_fallback(self):
        cause = DiseasePredictor._generate_causes('X', {'name': 'Mystery disease'})
        assert 'Pathogen infection' in cause


class TestBuildPrediction:
    """DiseasePredictor._build_prediction output shape."""

    def test_output_keys(self, mock_class_indices, mock_disease_info):
        # Patch tf import inside DiseasePredictor.__init__
        with patch('model_loader.tf') as mock_tf:
            mock_model = MagicMock()
            mock_tf.keras.models.load_model.return_value = mock_model
            dp = DiseasePredictor.__new__(DiseasePredictor)
            dp.class_indices = mock_class_indices
            dp.idx_to_class = {v: k for k, v in mock_class_indices.items()}
            dp.disease_info = mock_disease_info
            dp.model = None

            pred = dp._build_prediction('Tomato___healthy', 0.92)
            assert pred['disease'] == 'Tomato - Healthy'
            assert pred['confidence'] == 0.92
            assert pred['crop'] == 'Tomato'
            assert pred['is_healthy'] is True
            assert pred['severity'] == 'None'
            assert isinstance(pred['symptoms'], list)
            assert isinstance(pred['recommendation'], list)
            assert 'prevention' in pred
            assert 'causes' in pred


class TestLoadModels:
    """Model loading orchestrator."""

    def test_prefers_finetuned_when_exists(self, tmp_path, monkeypatch):
        base = tmp_path / 'best_model.keras'
        finetuned = tmp_path / 'best_model_finetuned.keras'
        base.write_bytes(b'base')
        finetuned.write_bytes(b'finetuned')

        indices = tmp_path / 'class_indices.json'
        indices.write_text(json.dumps({'A': 0}))

        class FakeConfig:
            MODEL_PATH = str(base)
            CLASS_INDICES_PATH = str(indices)
            DISEASE_INFO_PATH = str(tmp_path / 'nonexistent.json')
            LEAF_DETECTOR_PATH = str(tmp_path / 'nonexistent.keras')
            LEAF_DETECTOR_CONFIG = str(tmp_path / 'nonexistent.json')

        with patch('model_loader.tf') as mock_tf:
            mock_model = MagicMock()
            mock_tf.keras.models.load_model.return_value = mock_model
            predictor, leaf, loaded, leaf_loaded, engine = load_models(FakeConfig())
            # The model should have been loaded because finetuned exists
            assert loaded is True
            mock_tf.keras.models.load_model.assert_called_once()
            # Verify the path passed was the finetuned one
            call_args = mock_tf.keras.models.load_model.call_args[0][0]
            assert 'finetuned' in call_args

    def test_returns_none_when_no_model(self, tmp_path, monkeypatch):
        class FakeConfig:
            MODEL_PATH = str(tmp_path / 'missing.keras')
            CLASS_INDICES_PATH = str(tmp_path / 'missing.json')
            DISEASE_INFO_PATH = ''
            LEAF_DETECTOR_PATH = str(tmp_path / 'missing.keras')
            LEAF_DETECTOR_CONFIG = ''

        with patch('model_loader.tf', None):
            predictor, leaf, loaded, leaf_loaded, engine = load_models(FakeConfig())
            assert predictor is None
            assert loaded is False
