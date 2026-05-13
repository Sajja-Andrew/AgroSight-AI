"""Tests for pipeline/alerting.py AlertManager."""

import logging
from unittest.mock import MagicMock
import pytest

from pipeline.alerting import AlertManager


class TestAlertPerformanceDrop:
    """Performance drop alerts."""

    def test_logs_critical(self, caplog):
        with caplog.at_level(logging.CRITICAL):
            AlertManager.alert_performance_drop(
                {'accuracy': 0.80},
                {'accuracy': 0.90},
                -0.10
            )
        assert 'Performance drop detected' in caplog.text
        assert '0.8000' in caplog.text or '0.80' in caplog.text


class TestAlertPipelineFailure:
    """Pipeline failure alerts."""

    def test_logs_critical_with_stage(self, caplog):
        with caplog.at_level(logging.CRITICAL):
            AlertManager.alert_pipeline_failure('Disk full', stage='training')
        assert 'Pipeline failure at stage training' in caplog.text
        assert 'Disk full' in caplog.text

    def test_logs_critical_without_stage(self, caplog):
        with caplog.at_level(logging.CRITICAL):
            AlertManager.alert_pipeline_failure('Unknown error')
        assert 'Pipeline failure: Unknown error' in caplog.text


class TestAlertPostDeployDegradation:
    """Post-deployment degradation."""

    def test_logs_critical_when_significant_drop(self, caplog):
        with caplog.at_level(logging.CRITICAL):
            AlertManager.alert_post_deploy_degradation(0.85, 0.90)
        assert 'Post-deploy degradation detected' in caplog.text

    def test_skips_when_within_threshold(self, caplog):
        with caplog.at_level(logging.CRITICAL):
            AlertManager.alert_post_deploy_degradation(0.90, 0.90)
        assert 'Post-deploy degradation' not in caplog.text


class TestAlertInsufficientFeedback:
    """Insufficient feedback warning."""

    def test_logs_warning(self, caplog):
        with caplog.at_level(logging.WARNING):
            AlertManager.alert_insufficient_feedback(3, 5)
        assert 'Insufficient feedback for retraining' in caplog.text
        assert '3 < 5' in caplog.text
