"""
Alerting module.
Simple hooks for performance drops, pipeline failures, and post-deployment degradation.
"""

import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)


class AlertManager:
    """Emit alerts via logging (extendable to email/webhook)."""

    @staticmethod
    def alert_performance_drop(challenger_metrics: Dict[str, Any],
                                champion_metrics: Dict[str, Any],
                                delta: float):
        logger.critical(
            f"ALERT: Performance drop detected. "
            f"Challenger accuracy={challenger_metrics.get('accuracy'):.4f} "
            f"vs champion={champion_metrics.get('accuracy'):.4f} (delta={delta:.4f})"
        )

    @staticmethod
    def alert_pipeline_failure(error: str, stage: str = None):
        logger.critical(
            f"ALERT: Pipeline failure{' at stage ' + stage if stage else ''}: {error}"
        )

    @staticmethod
    def alert_post_deploy_degradation(current_accuracy: float, previous_accuracy: float):
        if current_accuracy < previous_accuracy * 0.95:
            logger.critical(
                f"ALERT: Post-deploy degradation detected. "
                f"Current accuracy={current_accuracy:.4f} vs previous={previous_accuracy:.4f}. "
                f"Consider rolling back."
            )

    @staticmethod
    def alert_insufficient_feedback(count: int, minimum: int):
        logger.warning(
            f"ALERT: Insufficient feedback for retraining ({count} < {minimum}). Skipping cycle."
        )
