"""Tests for backend/preprocessing.py image utilities."""

import io
import base64
import numpy as np
from PIL import Image
import pytest

from preprocessing import preprocess_image, preprocess_batch, decode_image


class TestPreprocessImage:
    """Single image preprocessing."""

    def test_returns_numpy_batch(self):
        img = Image.new('RGB', (300, 300), color=(50, 100, 150))
        result = preprocess_image(img, target_size=(224, 224))
        assert isinstance(result, np.ndarray)
        assert result.shape == (1, 224, 224, 3)

    def test_converts_rgba_to_rgb(self):
        img = Image.new('RGBA', (300, 300), color=(50, 100, 150, 200))
        result = preprocess_image(img, target_size=(224, 224))
        assert result.shape == (1, 224, 224, 3)

    def test_accepts_file_path(self, tmp_path):
        img_path = tmp_path / 'test.png'
        Image.new('RGB', (100, 100)).save(img_path)
        result = preprocess_image(str(img_path), target_size=(224, 224))
        assert result.shape == (1, 224, 224, 3)

    def test_accepts_numpy_array(self):
        arr = np.random.randint(0, 255, (100, 100, 3), dtype=np.uint8)
        result = preprocess_image(arr, target_size=(224, 224))
        assert result.shape == (1, 224, 224, 3)


class TestPreprocessBatch:
    """Batch preprocessing."""

    def test_batch_shape(self):
        images = [Image.new('RGB', (100, 100)) for _ in range(3)]
        result = preprocess_batch(images, target_size=(224, 224))
        assert result.shape == (3, 224, 224, 3)

    def test_mixed_input_types(self, tmp_path):
        img_path = tmp_path / 'test.png'
        Image.new('RGB', (100, 100)).save(img_path)
        images = [Image.new('RGB', (100, 100)), str(img_path), np.random.randint(0, 255, (100, 100, 3), dtype=np.uint8)]
        result = preprocess_batch(images, target_size=(224, 224))
        assert result.shape == (3, 224, 224, 3)


class TestDecodeImage:
    """Base64 / bytes decoding."""

    def test_decodes_base64(self):
        img = Image.new('RGB', (64, 64), color=(100, 150, 200))
        buf = io.BytesIO()
        img.save(buf, format='PNG')
        b64 = base64.b64encode(buf.getvalue()).decode('ascii')
        result = decode_image(b64)
        assert isinstance(result, Image.Image)
        assert result.mode == 'RGB'
        assert result.size == (64, 64)

    def test_decodes_data_uri(self):
        img = Image.new('RGB', (64, 64), color=(100, 150, 200))
        buf = io.BytesIO()
        img.save(buf, format='PNG')
        b64 = base64.b64encode(buf.getvalue()).decode('ascii')
        data_uri = f'data:image/png;base64,{b64}'
        result = decode_image(data_uri)
        assert isinstance(result, Image.Image)
        assert result.mode == 'RGB'

    def test_decodes_raw_bytes(self):
        img = Image.new('RGB', (64, 64), color=(100, 150, 200))
        buf = io.BytesIO()
        img.save(buf, format='PNG')
        raw = buf.getvalue()
        result = decode_image(raw)
        assert isinstance(result, Image.Image)
