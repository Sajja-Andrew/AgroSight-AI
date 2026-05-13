"""
Model Retraining module.
Supports incremental fine-tuning on the champion model or full retraining
from scratch using the existing CropDiseaseModel architecture.
"""

import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional

import numpy as np
import tensorflow as tf
from tensorflow.keras.callbacks import EarlyStopping, ReduceLROnPlateau, ModelCheckpoint
from sklearn.utils.class_weight import compute_class_weight

from . import config

logger = logging.getLogger(__name__)


class FeedbackRetrainer:
    """Retrain a classifier on original data + feedback images."""

    def __init__(self,
                 model_save_dir: Path = None,
                 epochs: int = None,
                 batch_size: int = None,
                 learning_rate: float = None,
                 fine_tune_layers: int = None):
        self.model_save_dir = Path(model_save_dir) if model_save_dir else config.MODEL_SAVE_DIR
        self.epochs = epochs if epochs is not None else config.DEFAULT_EPOCHS
        self.batch_size = batch_size if batch_size is not None else config.DEFAULT_BATCH_SIZE
        self.learning_rate = learning_rate if learning_rate is not None else config.DEFAULT_LEARNING_RATE
        self.fine_tune_layers = fine_tune_layers if fine_tune_layers is not None else config.DEFAULT_FINE_TUNE_LAYERS
        self.history = None
        self.model = None
        self.timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

    def retrain(self, train_data, val_data, mode: str = 'incremental',
                base_model_path: Path = None) -> Dict[str, Any]:
        """
        Retrain the model.
        mode: 'incremental' (fine-tune champion) or 'full' (train from scratch).
        Returns metadata about the training run.
        """
        self.timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

        if mode == 'incremental':
            self.model = self._load_champion(base_model_path)
            self._setup_incremental_training()
        elif mode == 'full':
            self.model = self._build_new_model(num_classes=len(train_data.class_indices))
        else:
            raise ValueError(f"Unknown mode: {mode}")

        # Compute class weights
        class_weight = self._compute_class_weights(train_data)

        # Callbacks
        callbacks = self._build_callbacks()

        logger.info(f"Starting {mode} training for {self.epochs} epochs")
        self.history = self.model.fit(
            train_data,
            epochs=self.epochs,
            validation_data=val_data,
            callbacks=callbacks,
            class_weight=class_weight,
            verbose=1
        )

        # Save final model with timestamp
        final_path = self.model_save_dir / f'feedback_retrain_{self.timestamp}.keras'
        self.model.save(str(final_path))
        logger.info(f"Final model saved to {final_path}")

        return {
            'mode': mode,
            'timestamp': self.timestamp,
            'epochs_requested': self.epochs,
            'epochs_trained': len(self.history.history['loss']),
            'final_accuracy': float(self.history.history['accuracy'][-1]),
            'final_val_accuracy': float(self.history.history['val_accuracy'][-1]),
            'final_loss': float(self.history.history['loss'][-1]),
            'final_val_loss': float(self.history.history['val_loss'][-1]),
            'model_path': str(final_path),
            'history': {k: [float(v) for v in vals] for k, vals in self.history.history.items()},
        }

    def _load_champion(self, base_model_path: Path = None) -> tf.keras.Model:
        path = base_model_path or config.CHAMPION_MODEL_PATH
        if not path.exists():
            path = config.FALLBACK_MODEL_PATH
        if not path.exists():
            raise FileNotFoundError(f"No champion model found at {path}")
        logger.info(f"Loading champion model from {path}")
        return tf.keras.models.load_model(str(path))

    def _setup_incremental_training(self):
        """Unfreeze top layers and recompile with low learning rate."""
        self.model.trainable = True
        # Freeze all layers except last N in the backbone
        for layer in self.model.layers:
            if any(name in layer.name.lower() for name in ('mobilenet', 'efficientnet', 'resnet')):
                if hasattr(layer, 'layers'):
                    for sub in layer.layers[:-self.fine_tune_layers]:
                        sub.trainable = False
        self.model.compile(
            optimizer=tf.keras.optimizers.Adam(learning_rate=self.learning_rate),
            loss='categorical_crossentropy',
            metrics=['accuracy']
        )
        logger.info(f"Model recompiled for incremental training (LR={self.learning_rate})")

    def _build_new_model(self, num_classes: int) -> tf.keras.Model:
        """Build a fresh transfer learning model."""
        from model.model import CropDiseaseModel
        crop_model = CropDiseaseModel(num_classes=num_classes, input_shape=(224, 224, 3))
        crop_model.build_transfer_learning_model('MobileNetV2')
        crop_model.compile_model(learning_rate=0.001)
        logger.info(f"Built new transfer learning model with {num_classes} classes")
        return crop_model.model

    def _compute_class_weights(self, train_data) -> Optional[Dict[int, float]]:
        try:
            labels = train_data.classes
            class_weights = compute_class_weight(
                class_weight='balanced',
                classes=np.unique(labels),
                y=labels
            )
            return dict(enumerate(class_weights))
        except Exception as e:
            logger.warning(f"Could not compute class weights: {e}")
            return None

    def _build_callbacks(self):
        checkpoint_path = self.model_save_dir / f'feedback_best_{self.timestamp}.keras'
        return [
            ModelCheckpoint(
                filepath=str(checkpoint_path),
                monitor='val_accuracy',
                save_best_only=True,
                mode='max',
                verbose=1
            ),
            EarlyStopping(
                monitor='val_loss',
                patience=3,
                restore_best_weights=True,
                verbose=1
            ),
            ReduceLROnPlateau(
                monitor='val_loss',
                factor=0.5,
                patience=2,
                min_lr=1e-8,
                verbose=1
            ),
        ]
