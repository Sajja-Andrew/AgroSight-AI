"""
Evaluation module.
Measures performance using accuracy, precision, recall, and F1-score.
Compares challenger with champion on the same validation set.
Implements the promotion gate.
"""

import json
import logging
from pathlib import Path
from typing import Dict, Any, Tuple

import numpy as np
import tensorflow as tf
from tensorflow.keras.preprocessing.image import ImageDataGenerator
from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score

from . import config

logger = logging.getLogger(__name__)


class ModelEvaluator:
    """Evaluate a model and compare it against the deployed champion."""

    def __init__(self, val_dir: Path, batch_size: int = None):
        self.val_dir = val_dir
        self.batch_size = batch_size or config.DEFAULT_BATCH_SIZE
        self.class_indices: Dict[str, int] = {}
        self.idx_to_class: Dict[int, str] = {}

    def _make_val_generator(self):
        """Create a fresh validation generator (deterministic, no shuffle)."""
        datagen = ImageDataGenerator()
        val_data = datagen.flow_from_directory(
            str(self.val_dir),
            target_size=(224, 224),
            batch_size=self.batch_size,
            class_mode='categorical',
            shuffle=False
        )
        self.class_indices = val_data.class_indices
        self.idx_to_class = {v: k for k, v in self.class_indices.items()}
        return val_data

    def evaluate(self, model_path: Path) -> Dict[str, Any]:
        """Evaluate a single model on the validation set."""
        logger.info(f"Evaluating model: {model_path}")
        model = tf.keras.models.load_model(str(model_path))
        val_data = self._make_val_generator()

        # Predict
        y_pred_probs = model.predict(val_data, verbose=0)
        y_pred = np.argmax(y_pred_probs, axis=1)

        # Ground truth
        val_data.reset()
        y_true = val_data.classes

        # In case of slight length mismatch due to generator rounding, trim
        min_len = min(len(y_true), len(y_pred))
        y_true = y_true[:min_len]
        y_pred = y_pred[:min_len]

        metrics = self._compute_metrics(y_true, y_pred)
        metrics['model_path'] = str(model_path)
        metrics['samples'] = min_len
        return metrics

    def _compute_metrics(self, y_true: np.ndarray, y_pred: np.ndarray) -> Dict[str, float]:
        return {
            'accuracy': float(accuracy_score(y_true, y_pred)),
            'precision_macro': float(precision_score(y_true, y_pred, average='macro', zero_division=0)),
            'recall_macro': float(recall_score(y_true, y_pred, average='macro', zero_division=0)),
            'f1_macro': float(f1_score(y_true, y_pred, average='macro', zero_division=0)),
            'precision_weighted': float(precision_score(y_true, y_pred, average='weighted', zero_division=0)),
            'recall_weighted': float(recall_score(y_true, y_pred, average='weighted', zero_division=0)),
            'f1_weighted': float(f1_score(y_true, y_pred, average='weighted', zero_division=0)),
        }

    def compare(self, challenger_path: Path, champion_path: Path = None) -> Tuple[Dict[str, Any], bool]:
        """
        Evaluate challenger vs champion on the same validation set.
        Returns (comparison_result, should_promote).
        """
        champion_path = champion_path or config.CHAMPION_MODEL_PATH
        if not champion_path.exists():
            champion_path = config.FALLBACK_MODEL_PATH

        challenger_metrics = self.evaluate(challenger_path)

        if not champion_path.exists():
            logger.warning("No champion model found; promoting challenger by default")
            return {
                'challenger': challenger_metrics,
                'champion': None,
                'delta_accuracy': 0.0,
                'promotion_reason': 'no_champion',
            }, True

        champion_metrics = self.evaluate(champion_path)

        delta_accuracy = challenger_metrics['accuracy'] - champion_metrics['accuracy']
        delta_f1 = challenger_metrics['f1_macro'] - champion_metrics['f1_macro']

        should_promote = delta_accuracy >= config.IMPROVEMENT_THRESHOLD

        result = {
            'challenger': challenger_metrics,
            'champion': champion_metrics,
            'delta_accuracy': round(delta_accuracy, 6),
            'delta_f1_macro': round(delta_f1, 6),
            'improvement_threshold': config.IMPROVEMENT_THRESHOLD,
            'should_promote': should_promote,
            'promotion_reason': 'accuracy_improved' if should_promote else 'below_threshold',
        }

        logger.info(
            f"Comparison: challenger_acc={challenger_metrics['accuracy']:.4f}, "
            f"champion_acc={champion_metrics['accuracy']:.4f}, "
            f"delta={delta_accuracy:.4f}, promote={should_promote}"
        )
        return result, should_promote
