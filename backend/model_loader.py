"""
Smart Crop AI - Centralized Model Loader
Loads Keras disease model and leaf detector with unified interface.
"""

import os
import json
import logging

try:
    import tensorflow as tf
    import numpy as np
    TF_AVAILABLE = True
except ImportError:
    TF_AVAILABLE = False
    tf = None
    np = None

from preprocessing import preprocess_image

logger = logging.getLogger(__name__)


class DiseasePredictor:
    """Keras-based disease predictor with structured output."""

    def __init__(self, model_path, class_indices_path, disease_info_path=None):
        logger.info(f"Loading model from: {model_path}")
        if not TF_AVAILABLE:
            raise RuntimeError("TensorFlow is required for DiseasePredictor")
        self.model = tf.keras.models.load_model(model_path)
        self.img_size = (224, 224)

        with open(class_indices_path, 'r') as f:
            self.class_indices = json.load(f)
        self.idx_to_class = {v: k for k, v in self.class_indices.items()}

        self.disease_info = {}
        if disease_info_path and os.path.exists(disease_info_path):
            with open(disease_info_path, 'r', encoding='utf-8') as f:
                self.disease_info = json.load(f)
        else:
            # fallback to disease_database.json
            fallback = os.path.join(os.path.dirname(__file__), 'data', 'disease_database.json')
            if os.path.exists(fallback):
                with open(fallback, 'r', encoding='utf-8') as f:
                    self.disease_info = json.load(f)

        logger.info(f"Model loaded. Classes: {len(self.class_indices)}")

    def predict(self, image, top_k=3):
        img_batch = preprocess_image(image, target_size=self.img_size)
        predictions = self.model.predict(img_batch, verbose=0)[0]
        top_indices = np.argsort(predictions)[::-1][:top_k]

        pred_list = []
        for idx in top_indices:
            class_name = self.idx_to_class[idx]
            confidence = float(predictions[idx])
            pred_list.append(self._build_prediction(class_name, confidence))

        primary = pred_list[0]
        return self._format_response(primary, pred_list)

    def _build_prediction(self, class_name, confidence):
        crop = self._extract_crop(class_name)
        disease_data = self.disease_info.get(class_name, {
            'name': class_name.replace('___', ' - ').replace('_', ' '),
            'symptoms': 'Information not available',
            'solution': 'Consult an agricultural expert',
            'prevention': 'Practice good agricultural methods',
            'severity': 'Unknown'
        })
        disease_name = disease_data.get('name', class_name.replace('___', ' - ').replace('_', ' '))
        is_healthy = 'healthy' in disease_name.lower()
        severity = self._resolve_severity(disease_data.get('severity', 'Unknown'), confidence, is_healthy)

        return {
            'disease': disease_name,
            'confidence': round(confidence, 4),
            'class_name': class_name,
            'crop': crop,
            'symptoms': self._split_to_list(disease_data.get('symptoms', 'Information not available')),
            'recommendation': self._split_to_list(disease_data.get('solution', 'Consult an agricultural expert')),
            'prevention': disease_data.get('prevention', 'Practice good agricultural methods.'),
            'causes': self._generate_causes(class_name, disease_data),
            'severity': severity,
            'is_healthy': is_healthy
        }

    def _format_response(self, primary, all_predictions):
        return {
            'success': True,
            'is_leaf': True,
            'crop': primary['crop'],
            'disease': primary['disease'],
            'confidence': primary['confidence'],
            'severity': primary['severity'],
            'symptoms': primary['symptoms'],
            'causes': primary['causes'],
            'recommendation': primary['recommendation'],
            'prevention': primary['prevention'],
            'is_healthy': primary['is_healthy'],
            'message': 'You can ask me any question about this result or your crop.',
            'predictions': all_predictions,
            'primary_prediction': primary
        }

    @staticmethod
    def _extract_crop(class_name):
        if '___' in class_name:
            return class_name.split('___')[0].replace('_', ' ')
        elif '_' in class_name:
            return class_name.split('_')[0].replace('_', ' ')
        return 'Unknown Crop'

    @staticmethod
    def _resolve_severity(db_severity, confidence, is_healthy):
        if is_healthy:
            return 'None'
        db_severity = (db_severity or 'Unknown').strip()
        if db_severity and db_severity.lower() not in ('unknown', '', 'n/a'):
            s = db_severity.lower()
            if 'high' in s or 'severe' in s:
                return 'Severe'
            elif 'medium' in s or 'moderate' in s:
                return 'Moderate'
            elif 'low' in s or 'mild' in s:
                return 'Mild'
            elif 'none' in s:
                return 'None'
        conf_pct = confidence * 100
        if conf_pct >= 76:
            return 'Severe'
        elif conf_pct >= 41:
            return 'Moderate'
        else:
            return 'Mild'

    @staticmethod
    def _split_to_list(text):
        if not text:
            return []
        import re
        parts = re.split(r'[.;]+', text)
        items = []
        for p in parts:
            p = p.strip()
            p = re.sub(r'^[-*•◦–—]+\s*', '', p)
            if len(p) > 3:
                items.append(p)
        return items if items else [text.strip()]

    @staticmethod
    def _generate_causes(class_name, disease_data):
        existing = disease_data.get('causes')
        if existing and existing.strip() and existing.strip().lower() not in ('information not available', ''):
            return existing.strip()
        disease_lower = disease_data.get('name', class_name).lower()
        if 'bacterial' in disease_lower or 'bacteria' in disease_lower:
            return 'Bacterial infection caused by pathogenic bacteria entering through wounds or natural openings, favored by warm, wet conditions.'
        if 'fungal' in disease_lower or 'mildew' in disease_lower or 'blight' in disease_lower or 'rust' in disease_lower or 'spot' in disease_lower:
            return 'Fungal infection spread by spores through wind, rain, or contaminated tools. Favored by high humidity and poor air circulation.'
        if 'virus' in disease_lower or 'mosaic' in disease_lower or 'curl' in disease_lower:
            return 'Viral infection transmitted by insect vectors (aphids, whiteflies) or through infected seeds and tools.'
        if 'mite' in disease_lower or 'spider' in disease_lower or 'insect' in disease_lower:
            return 'Pest infestation caused by mites or insects feeding on plant tissue, often exacerbated by dry conditions.'
        if 'healthy' in disease_lower:
            return 'No disease detected. The plant appears to be in good health.'
        return 'Pathogen infection or environmental stress under favorable conditions such as high humidity, poor drainage, or plant stress.'

    def predict_batch(self, images):
        return [self.predict(img) for img in images]


def load_models(config):
    """Load disease model and leaf detector from config paths."""
    import warnings
    warnings.filterwarnings('ignore', category=RuntimeWarning)

    predictor = None
    leaf_detector = None
    model_loaded = False
    leaf_model_loaded = False
    leaf_detector_method = 'none'
    model_engine = 'Mock'

    # Prefer finetuned champion if available, else fall back to base best_model
    model_path = config.MODEL_PATH
    finetuned_path = os.path.join(os.path.dirname(model_path), 'best_model_finetuned.keras')
    if os.path.exists(finetuned_path):
        model_path = finetuned_path
        logger.info(f"Using finetuned champion model: {model_path}")

    # Try Keras
    if TF_AVAILABLE and os.path.exists(model_path) and os.path.exists(config.CLASS_INDICES_PATH):
        try:
            predictor = DiseasePredictor(
                model_path=model_path,
                class_indices_path=config.CLASS_INDICES_PATH,
                disease_info_path=config.DISEASE_INFO_PATH if os.path.exists(config.DISEASE_INFO_PATH) else None
            )
            model_loaded = True
            model_engine = 'Keras'
            logger.info("Keras disease model loaded successfully")
        except Exception as e:
            logger.error(f"Failed to load Keras model: {e}")

    if predictor is None:
        logger.warning("No disease model loaded. Using mock predictions.")

    # Leaf detector — functional whether CNN model or heuristic is used
    try:
        from model.leaf_detector import LeafDetector
        if os.path.exists(config.LEAF_DETECTOR_PATH):
            leaf_detector = LeafDetector(
                model_path=config.LEAF_DETECTOR_PATH,
                config_path=config.LEAF_DETECTOR_CONFIG,
                threshold=0.7
            )
            if leaf_detector.model is not None:
                leaf_model_loaded = True
                leaf_detector_method = 'cnn'
                logger.info("Leaf detector loaded with CNN model")
            else:
                leaf_model_loaded = True  # Heuristic is a valid detection method
                leaf_detector_method = 'heuristic'
                logger.info("Leaf detector using heuristic fallback (CNN model could not load)")
        else:
            leaf_detector = LeafDetector(model_path=None, threshold=0.7)
            leaf_model_loaded = True  # Heuristic is functional
            leaf_detector_method = 'heuristic'
            logger.info("Leaf detector using heuristic fallback (no model file)")
    except Exception as e:
        logger.warning(f"Leaf detector not loaded: {e}")
        leaf_model_loaded = False
        leaf_detector_method = 'none'

    return predictor, leaf_detector, model_loaded, leaf_model_loaded, model_engine
