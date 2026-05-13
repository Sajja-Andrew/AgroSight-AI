"""
Unit tests for pipeline.validation.FeedbackValidator.
"""

import json
import tempfile
from pathlib import Path

from pipeline.validation import FeedbackValidator


class TestFeedbackValidator:
    """Test the validation stage of the feedback pipeline."""

    def test_is_verified_accepts_verified(self):
        v = FeedbackValidator()
        assert v._is_verified({'status': 'verified'}) is True
        assert v._is_verified({'status': 'approved'}) is True
        assert v._is_verified({'status': 'stored'}) is True

    def test_is_verified_rejects_unverified(self):
        v = FeedbackValidator()
        assert v._is_verified({'status': 'pending'}) is False
        assert v._is_verified({'status': ''}) is False

    def test_remove_duplicates(self):
        v = FeedbackValidator()
        entries = [
            {'id': '1', 'correct_class': 'A', 'timestamp': '2024-01-01', 'source': 'user_feedback'},
            {'id': '1', 'correct_class': 'A', 'timestamp': '2024-01-01', 'source': 'user_feedback'},
            {'id': '2', 'correct_class': 'B', 'timestamp': '2024-01-02', 'source': 'user_feedback'},
        ]
        deduped = v._remove_duplicates(entries)
        assert len(deduped) == 2

    def test_has_valid_class_with_loaded_indices(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump({'Tomato___healthy': 0, 'Potato___Late_blight': 1}, f)
            tmp_path = f.name

        v = FeedbackValidator(class_indices_path=Path(tmp_path))
        assert v._has_valid_class({'correct_class': 'Tomato___healthy'}) is True
        assert v._has_valid_class({'correct_class': 'Unknown'}) is False

        Path(tmp_path).unlink()

    def test_detect_inconsistencies(self):
        v = FeedbackValidator()
        entries = [
            {'id': 'img1', 'correct_class': 'A', 'image_path': 'img1.jpg'},
            {'id': 'img1_dup', 'correct_class': 'B', 'image_path': 'img1.jpg'},
            {'id': 'img2', 'correct_class': 'A', 'image_path': 'img2.jpg'},
        ]
        clean, quarantined = v._detect_inconsistencies(entries)
        assert len(quarantined) == 2  # both img1 entries
        assert len(clean) == 1  # only img2

    def test_validate_full_pipeline(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump({'A': 0, 'B': 1}, f)
            tmp_path = f.name

        v = FeedbackValidator(class_indices_path=Path(tmp_path))
        entries = [
            {'id': '1', 'predicted_class': 'X', 'correct_class': 'A', 'confidence': 80, 'timestamp': '2024-01-01', 'source': 'user_feedback', 'status': 'verified', 'image_path': 'img1.jpg'},
            {'id': '2', 'predicted_class': 'X', 'correct_class': 'A', 'confidence': 80, 'timestamp': '2024-01-02', 'source': 'user_feedback', 'status': 'verified', 'image_path': 'img2.jpg'},
            {'id': '3', 'predicted_class': 'X', 'correct_class': 'C', 'confidence': 80, 'timestamp': '2024-01-03', 'source': 'user_feedback', 'status': 'verified'},
        ]
        clean, stats = v.validate(entries)
        assert stats['raw_count'] == 3
        assert stats['after_duplicate_removal'] == 3  # all distinct
        assert stats['after_class_validation'] == 2  # 'C' filtered out
        assert stats['final_count'] == 2
        assert len(clean) == 2

        Path(tmp_path).unlink()
