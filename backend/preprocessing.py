"""
Smart Crop AI - Centralized Image Preprocessing
Ensures training and inference use identical transforms.
Includes NaN/Inf protection and safe normalization.
"""

import warnings
import numpy as np
from PIL import Image

# Suppress numpy runtime warnings during preprocessing
warnings.filterwarnings('ignore', category=RuntimeWarning)

_EPS = 1e-7  # Small constant for numerical stability


def preprocess_image(image, target_size=(224, 224)):
    """
    Preprocess a PIL Image for the Keras model.

    Steps:
    1. Convert to RGB
    2. Resize to target_size
    3. Convert to numpy array (float32)
    4. Clamp to valid range [0, 255]
    5. Add batch dimension

    NOTE: We do NOT divide by 255 here because the model includes
    tf.keras.applications.mobilenet_v2.preprocess_input inside the graph.
    """
    if isinstance(image, str):
        image = Image.open(image)
    if isinstance(image, np.ndarray):
        image = Image.fromarray(image)

    # Ensure RGB
    if image.mode != 'RGB':
        image = image.convert('RGB')

    # Resize
    image = image.resize(target_size, Image.LANCZOS)

    # To numpy array (float32, 0-255)
    img_array = np.array(image, dtype=np.float32)

    # Clamp to valid pixel range
    img_array = np.clip(img_array, 0.0, 255.0)

    # Replace any NaN or Inf values
    img_array = np.where(np.isfinite(img_array), img_array, 0.0)

    # Add batch dimension
    img_batch = np.expand_dims(img_array, axis=0)

    return img_batch


def preprocess_batch(images, target_size=(224, 224)):
    """Preprocess a list of PIL Images into a single batch array."""
    arrays = []
    for image in images:
        arr = preprocess_image(image, target_size=target_size)
        arrays.append(arr[0])  # Remove batch dim
    batch = np.stack(arrays, axis=0)
    batch = np.where(np.isfinite(batch), batch, 0.0)
    return batch


def decode_image(data):
    """Decode base64 string or raw bytes into PIL Image."""
    import base64
    import io
    if isinstance(data, str):
        if 'base64,' in data:
            data = data.split('base64,')[1]
        image_bytes = base64.b64decode(data)
    else:
        image_bytes = data
    image = Image.open(io.BytesIO(image_bytes))
    if image.mode != 'RGB':
        image = image.convert('RGB')
    return image
