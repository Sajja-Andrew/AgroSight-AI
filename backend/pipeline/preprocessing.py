"""
Preprocessing module.
Assembles a unified dataset from original training data + validated feedback images,
splits into train/val, and prepares ImageDataGenerator configurations.
"""

import json
import logging
import os
import shutil
from pathlib import Path
from typing import List, Dict, Any, Tuple

try:
    from sklearn.model_selection import train_test_split
except ImportError:
    train_test_split = None

try:
    from tensorflow.keras.preprocessing.image import ImageDataGenerator
except ImportError:
    ImageDataGenerator = None

from . import config

logger = logging.getLogger(__name__)


class DatasetBuilder:
    """Build a unified, reproducible dataset for retraining."""

    def __init__(self,
                 original_data_dir: Path = None,
                 feedback_processed_dir: Path = None,
                 train_split: float = None,
                 random_seed: int = None):
        self.original_data_dir = Path(original_data_dir) if original_data_dir else config.ORIGINAL_DATA_DIR
        self.feedback_processed_dir = Path(feedback_processed_dir) if feedback_processed_dir else config.FEEDBACK_PROCESSED_DIR
        self.train_split = train_split if train_split is not None else config.TRAIN_SPLIT
        self.random_seed = random_seed if random_seed is not None else config.RANDOM_SEED
        self.manifest: Dict[str, Any] = {}

    def build(self, feedback_entries: List[Dict[str, Any]], use_original: bool = True) -> Tuple[Path, Path]:
        """
        Build train/val directories from original data + feedback images.
        Returns (train_dir, val_dir) pointing into feedback_processed_dir.
        """
        if train_test_split is None:
            raise ImportError("scikit-learn is required for dataset building. Install: pip install scikit-learn")

        # Clean and prepare output dirs
        for split in ('train', 'val'):
            split_dir = self.feedback_processed_dir / split
            if split_dir.exists():
                shutil.rmtree(split_dir)
            split_dir.mkdir(parents=True, exist_ok=True)

        # Gather all image paths with their classes
        samples: List[Tuple[str, Path]] = []  # (class_name, image_path)

        # 1. Original training data
        if use_original:
            orig_train = self.original_data_dir / 'train'
            if orig_train.exists():
                for class_dir in orig_train.iterdir():
                    if not class_dir.is_dir():
                        continue
                    for img_file in class_dir.iterdir():
                        if img_file.is_file() and self._is_image(img_file):
                            samples.append((class_dir.name, img_file))
                logger.info(f"Added {len(samples)} original training samples")

        # 2. Feedback images
        feedback_samples = self._collect_feedback_images(feedback_entries)
        samples.extend(feedback_samples)
        logger.info(f"Added {len(feedback_samples)} feedback samples")

        if not samples:
            logger.warning("No samples available for dataset build")
            return self.feedback_processed_dir / 'train', self.feedback_processed_dir / 'val'

        # 3. Reproducible train/val split
        classes = [s[0] for s in samples]
        paths = [s[1] for s in samples]
        train_paths, val_paths, train_classes, val_classes = train_test_split(
            paths, classes, train_size=self.train_split, random_state=self.random_seed, stratify=classes
        )

        # 4. Copy to processed directory
        for split_name, split_paths, split_classes in [('train', train_paths, train_classes), ('val', val_paths, val_classes)]:
            for p, cls in zip(split_paths, split_classes):
                dest_dir = self.feedback_processed_dir / split_name / cls
                dest_dir.mkdir(parents=True, exist_ok=True)
                shutil.copy2(p, dest_dir / p.name)

        # 5. Manifest for traceability
        self.manifest = {
            'random_seed': self.random_seed,
            'train_split': self.train_split,
            'total_samples': len(samples),
            'train_count': len(train_paths),
            'val_count': len(val_paths),
            'num_classes': len(set(classes)),
            'feedback_count': len(feedback_samples),
            'original_count': len(samples) - len(feedback_samples),
        }
        manifest_path = self.feedback_processed_dir / 'dataset_manifest.json'
        with open(manifest_path, 'w', encoding='utf-8') as f:
            json.dump(self.manifest, f, indent=2)
        logger.info(f"Dataset manifest saved to {manifest_path}")

        return self.feedback_processed_dir / 'train', self.feedback_processed_dir / 'val'

    def _collect_feedback_images(self, entries: List[Dict[str, Any]]) -> List[Tuple[str, Path]]:
        """Collect actual image files from feedback entries."""
        samples = []
        for e in entries:
            img_path = e.get('image_path')
            if not img_path:
                continue
            p = Path(img_path)
            if not p.exists():
                # Try resolving relative to backend dir
                p = Path(config.BACKEND_DIR) / img_path
            if p.exists() and p.is_file() and self._is_image(p):
                samples.append((e['correct_class'], p))
            else:
                logger.debug(f"Feedback image not found or not an image: {img_path}")
        return samples

    @staticmethod
    def _is_image(path: Path) -> bool:
        return path.suffix.lower() in {'.png', '.jpg', '.jpeg', '.gif', '.bmp', '.webp'}

    def get_data_generators(self, train_dir: Path, val_dir: Path, batch_size: int = None):
        """
        Create ImageDataGenerators. No rescaling — preprocess_input is baked into model.
        Returns (train_gen, val_gen, train_data, val_data).
        """
        if ImageDataGenerator is None:
            raise ImportError("tensorflow is required for data generators.")

        bs = batch_size or config.DEFAULT_BATCH_SIZE

        train_datagen = ImageDataGenerator(
            rotation_range=15,
            width_shift_range=0.1,
            height_shift_range=0.1,
            horizontal_flip=True,
            fill_mode='nearest'
        )
        val_datagen = ImageDataGenerator()

        train_data = train_datagen.flow_from_directory(
            str(train_dir),
            target_size=(224, 224),
            batch_size=bs,
            class_mode='categorical',
            shuffle=True
        )
        val_data = val_datagen.flow_from_directory(
            str(val_dir),
            target_size=(224, 224),
            batch_size=bs,
            class_mode='categorical',
            shuffle=False
        )
        return train_datagen, val_datagen, train_data, val_data

    def get_manifest(self) -> Dict[str, Any]:
        return self.manifest
