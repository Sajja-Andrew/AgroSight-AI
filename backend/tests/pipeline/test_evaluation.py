"""Tests for pipeline/evaluation.py ModelEvaluator."""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest
import numpy as np

from pipeline.evaluation import ModelEvaluator


class TestComputeMetrics:
    """Metric computation logic."""

    def test_perfect_prediction(self):
        y_true = np.array([0, 1, 2, 0, 1])
        y_pred = np.array([0, 1, 2, 0, 1])
        ev = ModelEvaluator.__new__(ModelEvaluator)
        m = ev._compute_metrics(y_true, y_pred)
        assert m['accuracy'] == 1.0
        assert m['precision_macro'] == 1.0
        assert m['recall_macro'] == 1.0
        assert m['f1_macro'] == 1.0

    def test_all_wrong(self):
        y_true = np.array([0, 0, 0])
        y_pred = np.array([1, 1, 1])
        ev = ModelEvaluator.__new__(ModelEvaluator)
        m = ev._compute_metrics(y_true, y_pred)
        assert m['accuracy'] == 0.0
        assert m['precision_macro'] == 0.0
        assert m['recall_macro'] == 0.0

    def test_zero_division_safe(self):
        y_true = np.array([0, 0, 0])
        y_pred = np.array([0, 0, 0])
        ev = ModelEvaluator.__new__(ModelEvaluator)
        m = ev._compute_metrics(y_true, y_pred)
        assert m['accuracy'] == 1.0


class TestCompare:
    """Challenger vs champion comparison."""

    def test_promotes_when_no_champion(self, tmp_path):
        challenger = tmp_path / 'challenger.keras'
        challenger.write_bytes(b'fake')

        with patch.object(ModelEvaluator, 'evaluate') as mock_eval, \
             patch('pipeline.evaluation.config.CHAMPION_MODEL_PATH', tmp_path / 'no_champion.keras'), \
             patch('pipeline.evaluation.config.FALLBACK_MODEL_PATH', tmp_path / 'no_fallback.keras'):
            mock_eval.return_value = {
                'accuracy': 0.85,
                'precision_macro': 0.84,
                'recall_macro': 0.83,
                'f1_macro': 0.83,
                'precision_weighted': 0.84,
                'recall_weighted': 0.83,
                'f1_weighted': 0.83,
            }
            ev = ModelEvaluator(tmp_path)
            result, should_promote = ev.compare(challenger, tmp_path / 'nonexistent.keras')
            assert should_promote is True
            assert result['promotion_reason'] == 'no_champion'

    def test_promotes_above_threshold(self, tmp_path):
        challenger = tmp_path / 'challenger.keras'
        champion = tmp_path / 'champion.keras'
        challenger.write_bytes(b'c')
        champion.write_bytes(b'c')

        with patch.object(ModelEvaluator, 'evaluate') as mock_eval:
            def side_effect(path):
                base = {
                    'accuracy': 0.90,
                    'precision_macro': 0.89,
                    'recall_macro': 0.88,
                    'f1_macro': 0.88,
                    'precision_weighted': 0.89,
                    'recall_weighted': 0.88,
                    'f1_weighted': 0.88,
                }
                if 'challenger' in str(path):
                    base['accuracy'] = 0.92
                return base
            mock_eval.side_effect = side_effect

            with patch('pipeline.evaluation.config.IMPROVEMENT_THRESHOLD', 0.01):
                ev = ModelEvaluator(tmp_path)
                result, should_promote = ev.compare(challenger, champion)
                assert should_promote is True
                assert result['promotion_reason'] == 'accuracy_improved'
                assert result['delta_accuracy'] == pytest.approx(0.02)

    def test_no_promotion_below_threshold(self, tmp_path):
        challenger = tmp_path / 'challenger.keras'
        champion = tmp_path / 'champion.keras'
        challenger.write_bytes(b'c')
        champion.write_bytes(b'c')

        with patch.object(ModelEvaluator, 'evaluate') as mock_eval:
            def side_effect(path):
                base = {
                    'accuracy': 0.90,
                    'precision_macro': 0.89,
                    'recall_macro': 0.88,
                    'f1_macro': 0.88,
                    'precision_weighted': 0.89,
                    'recall_weighted': 0.88,
                    'f1_weighted': 0.88,
                }
                if 'challenger' in str(path):
                    base['accuracy'] = 0.901
                return base
            mock_eval.side_effect = side_effect

            with patch('pipeline.evaluation.config.IMPROVEMENT_THRESHOLD', 0.01):
                ev = ModelEvaluator(tmp_path)
                result, should_promote = ev.compare(challenger, champion)
                assert should_promote is False
                assert result['promotion_reason'] == 'below_threshold'
