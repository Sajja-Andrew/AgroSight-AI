"""
Leaf Detector Inference Module
Binary classifier: Leaf vs Not Leaf
Production-ready with fallback heuristic when model is unavailable.
Includes comprehensive NaN/divide-by-zero protection and numerical stability.
"""

import os
import json
import numpy as np
import logging
from PIL import Image

logger = logging.getLogger(__name__)

# TensorFlow optional
try:
    import tensorflow as tf
    TF_AVAILABLE = True
except ImportError:
    TF_AVAILABLE = False
    tf = None


class LeafDetector:
    """
    Detects whether an image contains a plant leaf.

    Uses a trained CNN model when available.
    Falls back to a heuristic (green-pixel + shape analysis) when model is missing.
    Includes comprehensive NaN and division-by-zero protection.
    """

    def __init__(self, model_path=None, config_path=None, threshold=0.5):
        """
        Args:
            model_path: Path to .keras leaf detector model
            config_path: Path to leaf_detector_config.json
            threshold: Minimum confidence to accept as leaf (default 0.5 for heuristic, 0.7 for model)
        """
        self.model = None
        self.threshold = float(threshold)
        self.img_size = (224, 224)
        self.config = {}
        self.eps = 1e-7  # Small constant to prevent division by zero

        # Try to load model
        if model_path and os.path.exists(model_path) and TF_AVAILABLE:
            try:
                self.model = tf.keras.models.load_model(model_path, compile=False)
                logger.info(f"[LeafDetector] Model loaded successfully from: {model_path}")
            except Exception as e:
                logger.warning(f"[LeafDetector] Could not load model: {e}. Using heuristic fallback.")
                self.model = None
        else:
            if model_path:
                logger.warning(f"[LeafDetector] Model path not found: {model_path}")
            if not TF_AVAILABLE:
                logger.warning("[LeafDetector] TensorFlow not available. Using heuristic fallback.")
            else:
                logger.info("[LeafDetector] Using heuristic fallback for leaf detection.")

        # Load config if available
        if config_path and os.path.exists(config_path):
            try:
                with open(config_path, 'r') as f:
                    self.config = json.load(f)
                self.threshold = float(self.config.get('threshold', threshold))
                logger.info(f"[LeafDetector] Config loaded with threshold: {self.threshold}")
            except Exception as e:
                logger.warning(f"[LeafDetector] Could not load config: {e}")

    def predict(self, image):
        """
        Analyze image and return leaf detection result.

        Args:
            image: PIL Image, numpy array, or file path

        Returns:
            dict: {
                'is_leaf': bool,
                'confidence': float,  # probability that it IS a leaf [0, 1]
                'method': 'model' | 'heuristic',
                'message': str
            }
        """
        try:
            # Load image
            if isinstance(image, str):
                image = Image.open(image).convert('RGB')
            elif isinstance(image, np.ndarray):
                image = Image.fromarray(image.astype(np.uint8)).convert('RGB')
            else:
                image = image.convert('RGB')

            # CNN-based detection
            if self.model is not None and TF_AVAILABLE:
                return self._predict_with_model(image)
            else:
                return self._predict_with_heuristic(image)
        except Exception as e:
            logger.error(f"[LeafDetector] Prediction error: {e}")
            return {
                'is_leaf': True,  # Assume leaf on error (safer fallback)
                'confidence': 0.5,
                'method': 'error_fallback',
                'message': 'Leaf detection encountered an error. Proceeding with caution.'
            }

    def _predict_with_model(self, image):
        """Run CNN model prediction with NaN protection."""
        try:
            img = image.resize(self.img_size, Image.LANCZOS)
            img_array = np.array(img, dtype=np.float32)

            # Validate image data
            if np.any(np.isnan(img_array)) or np.any(np.isinf(img_array)):
                logger.warning("[LeafDetector] Image contains NaN/Inf values. Using heuristic.")
                return self._predict_with_heuristic(image)

            # MobileNetV2 preprocess_input
            img_array = tf.keras.applications.mobilenet_v2.preprocess_input(img_array)
            
            # Clamp values to prevent extreme outliers
            img_array = np.clip(img_array, -255.0, 255.0)
            
            img_batch = np.expand_dims(img_array, axis=0)

            # Predict
            prob_raw = self.model.predict(img_batch, verbose=0)[0][0]
            
            # Validate prediction output
            if np.isnan(prob_raw) or np.isinf(prob_raw):
                logger.warning("[LeafDetector] Model returned NaN/Inf. Using heuristic.")
                return self._predict_with_heuristic(image)
            
            # Clamp probability to [0, 1]
            prob = float(np.clip(prob_raw, 0.0, 1.0))

            is_leaf = prob >= self.threshold
            method = 'model'

            if is_leaf:
                message = f"Leaf detected with {prob*100:.1f}% confidence."
            else:
                message = f"Not a leaf ({(1-prob)*100:.1f}% confidence). Please upload a clear plant leaf image."

            return {
                'is_leaf': bool(is_leaf),
                'confidence': float(round(prob, 4)),
                'method': str(method),
                'message': str(message)
            }
        except Exception as e:
            logger.warning(f"[LeafDetector] Model prediction failed: {e}. Falling back to heuristic.")
            return self._predict_with_heuristic(image)

    def _predict_with_heuristic(self, image):
        """
        Fallback heuristic based on green-pixel dominance and texture analysis.
        Includes comprehensive NaN/divide-by-zero protection.
        """
        try:
            img = image.resize(self.img_size, Image.LANCZOS)
            arr = np.array(img, dtype=np.uint8)

            # Validate array
            if arr.size == 0 or np.any(np.isnan(arr)) or np.any(np.isinf(arr)):
                logger.warning("[LeafDetector] Invalid image array. Returning safe fallback.")
                return {
                    'is_leaf': True,
                    'confidence': 0.5,
                    'method': 'heuristic_error',
                    'message': 'Could not analyze image. Assuming leaf (safe mode).'
                }

            # Convert to HSV for better color analysis
            hsv = self._rgb_to_hsv(arr)

            if hsv is None or np.any(np.isnan(hsv)) or np.any(np.isinf(hsv)):
                logger.warning("[LeafDetector] HSV conversion failed. Using RGB analysis.")
                return self._analyze_rgb_fallback(arr)

            # Green pixels: Hue between 35 and 90 (OpenCV-style H:0-179)
            # Our HSV uses 0-255 range for H, so green is roughly 30-100
            h_channel = hsv[:, :, 0].astype(np.float32)
            s_channel = hsv[:, :, 1].astype(np.float32)
            v_channel = hsv[:, :, 2].astype(np.float32)

            # Green mask: hue in green range, sufficient saturation and value
            green_mask = (
                (h_channel > 30) & (h_channel < 100) &
                (s_channel > 40) &
                (v_channel > 30)
            ).astype(np.float32)

            green_ratio = float(np.mean(green_mask))
            if np.isnan(green_ratio) or np.isinf(green_ratio):
                green_ratio = 0.0

            # Texture analysis: leaves tend to have moderate edge density
            gray = np.mean(arr.astype(np.float32), axis=2)
            edges = self._sobel_edges(gray)
            
            if edges is None or np.any(np.isnan(edges)) or np.any(np.isinf(edges)):
                edge_density = 0.0
            else:
                edge_density = float(np.mean((edges > 20).astype(np.float32)))
                if np.isnan(edge_density) or np.isinf(edge_density):
                    edge_density = 0.0

            # Shape analysis: leaves usually occupy a connected central region
            green_coords = np.argwhere(green_mask > 0.5)
            if len(green_coords) > 10:  # Need sufficient green pixels
                y_min, x_min = green_coords.min(axis=0)
                y_max, x_max = green_coords.max(axis=0)
                bbox_area = float((x_max - x_min + 1) * (y_max - y_min + 1))
                bbox_ratio = min(bbox_area / (224.0 * 224.0), 1.0)
            else:
                bbox_ratio = 0.0

                # Composite score (calibrated against typical leaf images)
            # Improved weighting for heuristic mode
            score = (
                green_ratio * 0.50 +      # Green dominance (primary signal)
                edge_density * 0.30 +     # Edge density (more weight for texture)
                bbox_ratio * 0.20         # Bounding box (spatial coherence)
            )

            # Safety clamp
            score = float(np.clip(score, 0.0, 1.0))
            if np.isnan(score) or np.isinf(score):
                score = 0.5

            # Adaptive threshold: 0.4 for heuristic (sensitive), 0.7 for model (strict)
            threshold = 0.4 if self.model is None else self.threshold
            is_leaf = score >= threshold
            method = 'heuristic'

            if is_leaf:
                message = f"Leaf detected (heuristic score: {score:.2f})."
            else:
                message = f"This does not appear to be a plant leaf (heuristic score: {score:.2f}). Please upload a clear leaf image."

            return {
                'is_leaf': bool(is_leaf),
                'confidence': float(round(score, 4)),
                'method': str(method),
                'message': str(message)
            }
        except Exception as e:
            logger.error(f"[LeafDetector] Heuristic prediction failed: {e}")
            return {
                'is_leaf': True,
                'confidence': 0.5,
                'method': 'heuristic_error',
                'message': 'Leaf detection error. Proceeding with caution.'
            }

    def _analyze_rgb_fallback(self, arr):
        """Ultra-simple RGB-based fallback when HSV fails."""
        try:
            r = arr[:, :, 0].astype(np.float32)
            g = arr[:, :, 1].astype(np.float32)
            b = arr[:, :, 2].astype(np.float32)

            # Green dominance (primary signal)
            green_dominance = np.mean(g > np.maximum(r, b)).astype(np.float32)
            if np.isnan(green_dominance) or np.isinf(green_dominance):
                green_dominance = 0.0

            # Moderate green values (not too bright, not too dark)
            moderate_green = np.mean((g > 50) & (g < 200)).astype(np.float32)
            if np.isnan(moderate_green) or np.isinf(moderate_green):
                moderate_green = 0.0

            # Check for green on colored background (yellow spots = disease)
            yellow_mask = (g > r) & (r > b)
            yellow_ratio = np.mean(yellow_mask.astype(np.float32))

            score = (
                green_dominance * 0.50 +
                moderate_green * 0.35 +
                yellow_ratio * 0.15  # Diseased leaves have yellow spots
            )
            score = float(np.clip(score, 0.0, 1.0))

            # Use adaptive threshold
            threshold = 0.4
            is_leaf = score >= threshold

            return {
                'is_leaf': bool(is_leaf),
                'confidence': float(round(score, 4)),
                'method': 'rgb_fallback',
                'message': 'Leaf detected with RGB fallback analysis.' if is_leaf else f'Unclear leaf status (confidence: {score:.2f}). Please upload a clearer image.'
            }
        except Exception as e:
            logger.error(f"[LeafDetector] RGB fallback failed: {e}")
            return {
                'is_leaf': True,
                'confidence': 0.5,
                'method': 'critical_fallback',
                'message': 'Critical fallback: assuming leaf.'
            }

    def _rgb_to_hsv(self, rgb):
        """
        Convert RGB array (0-255) to HSV array (H:0-255, S:0-255, V:0-255).
        Includes comprehensive divide-by-zero and NaN protection.
        """
        try:
            rgb = rgb.astype(np.float32) / 255.0
            r, g, b = rgb[:, :, 0], rgb[:, :, 1], rgb[:, :, 2]

            mx = np.maximum(np.maximum(r, g), b)
            mn = np.minimum(np.minimum(r, g), b)
            df = mx - mn

            # Value
            v = mx

            # Saturation with divide-by-zero protection
            s = np.where(mx > self.eps, df / (mx + self.eps), 0.0)
            s = np.clip(s, 0.0, 1.0)

            # Hue with divide-by-zero protection
            h = np.zeros_like(mx)

            # Case 1: max == min (gray)
            cond = df < self.eps
            h = np.where(cond, 0, h)

            # Case 2: max == r
            cond = (mx == r) & (df >= self.eps)
            h = np.where(cond, (60 * np.fmod((g - b) / (df + self.eps), 6.0) + 360) % 360, h)

            # Case 3: max == g
            cond = (mx == g) & (df >= self.eps)
            h = np.where(cond, (60 * ((b - r) / (df + self.eps) + 2.0)) % 360, h)

            # Case 4: max == b
            cond = (mx == b) & (df >= self.eps)
            h = np.where(cond, (60 * ((r - g) / (df + self.eps) + 4.0)) % 360, h)

            # Validate
            h = np.clip(h, 0, 360)
            s = np.clip(s, 0, 1)
            v = np.clip(v, 0, 1)

            if np.any(np.isnan(h)) or np.any(np.isnan(s)) or np.any(np.isnan(v)):
                logger.warning("[LeafDetector] NaN detected in HSV conversion. Using fallback.")
                return None

            # Scale to 0-255
            hsv = np.stack([
                (h / 360.0) * 255.0,
                s * 255.0,
                v * 255.0
            ], axis=2).astype(np.uint8)

            return hsv
        except Exception as e:
            logger.error(f"[LeafDetector] RGB to HSV conversion error: {e}")
            return None

    def _sobel_edges(self, gray):
        """Apply Sobel edge detection with numerical stability."""
        try:
            # Ensure valid input
            gray = np.asarray(gray, dtype=np.float32)
            if np.any(np.isnan(gray)) or np.any(np.isinf(gray)):
                logger.warning("[LeafDetector] Invalid grayscale input for edge detection.")
                return None

            # Clamp values
            gray = np.clip(gray, 0, 255)

            # Simple Sobel operator
            sobel_x = np.array([[-1, 0, 1], [-2, 0, 2], [-1, 0, 1]], dtype=np.float32)
            sobel_y = np.array([[-1, -2, -1], [0, 0, 0], [1, 2, 1]], dtype=np.float32)

            try:
                from scipy.ndimage import convolve
                gx = convolve(gray, sobel_x, mode='constant', cval=0.0)
                gy = convolve(gray, sobel_y, mode='constant', cval=0.0)
            except ImportError:
                logger.warning("[LeafDetector] scipy not available. Using simple edge detection.")
                # Simple approximation without scipy
                gx = np.zeros_like(gray)
                gy = np.zeros_like(gray)
                for i in range(1, gray.shape[0] - 1):
                    for j in range(1, gray.shape[1] - 1):
                        gx[i, j] = (
                            -gray[i-1, j-1] + gray[i-1, j+1] -
                            2*gray[i, j-1] + 2*gray[i, j+1] -
                            gray[i+1, j-1] + gray[i+1, j+1]
                        )
                        gy[i, j] = (
                            -gray[i-1, j-1] - 2*gray[i-1, j] - gray[i-1, j+1] +
                            gray[i+1, j-1] + 2*gray[i+1, j] + gray[i+1, j+1]
                        )

            # Compute magnitude with numerical stability
            magnitude = np.sqrt(gx**2 + gy**2 + self.eps)

            if np.any(np.isnan(magnitude)) or np.any(np.isinf(magnitude)):
                logger.warning("[LeafDetector] NaN/Inf in edge magnitude. Clamping.")
                magnitude = np.clip(magnitude, 0, 255)

            return magnitude
        except Exception as e:
            logger.error(f"[LeafDetector] Sobel edge detection error: {e}")
            return None


def get_mock_leaf_result(is_leaf=True):
    """Return a mock leaf detection result for testing."""
    if is_leaf:
        return {
            'is_leaf': True,
            'confidence': 0.95,
            'method': 'mock',
            'message': 'Leaf detected (mock).'
        }
    return {
        'is_leaf': False,
        'confidence': 0.15,
        'method': 'mock',
        'message': 'This is not a plant leaf. Please upload a clear leaf image.'
    }
