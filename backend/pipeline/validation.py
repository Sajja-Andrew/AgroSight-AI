"""
Data Validation module.
Filters verified feedback, removes duplicates, detects inconsistent labels,
and validates against the known class index mapping.
"""

import hashlib
import json
import logging
from pathlib import Path
from typing import List, Dict, Any, Set, Tuple

from . import config

logger = logging.getLogger(__name__)


class FeedbackValidator:
    """Validate and clean feedback entries for training readiness."""

    def __init__(self, class_indices_path: Path = None):
        self.class_indices_path = class_indices_path or config.CLASS_INDICES_PATH
        self.valid_classes: Set[str] = set()
        self._load_class_indices()

    def _load_class_indices(self):
        if not self.class_indices_path.exists():
            logger.warning(f"class_indices.json not found; allowing all classes")
            return
        try:
            with open(self.class_indices_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            self.valid_classes = set(data.keys())
            logger.info(f"Loaded {len(self.valid_classes)} valid classes")
        except Exception as e:
            logger.error(f"Error loading class_indices: {e}")

    def validate(self, entries: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """
        Run validation pipeline.
        Returns: (clean_entries, stats_report)
        """
        stats = {
            'raw_count': len(entries),
            'after_status_filter': 0,
            'after_duplicate_removal': 0,
            'after_class_validation': 0,
            'after_consistency_filter': 0,
            'quarantined_inconsistent': 0,
            'final_count': 0,
        }

        # 1. Filter by status
        verified = [e for e in entries if self._is_verified(e)]
        stats['after_status_filter'] = len(verified)

        # 2. Remove duplicates
        deduped = self._remove_duplicates(verified)
        stats['after_duplicate_removal'] = len(deduped)

        # 3. Validate classes
        valid_classed = [e for e in deduped if self._has_valid_class(e)]
        stats['after_class_validation'] = len(valid_classed)

        # 4. Detect inconsistent labels
        clean, quarantined = self._detect_inconsistencies(valid_classed)
        stats['after_consistency_filter'] = len(clean)
        stats['quarantined_inconsistent'] = len(quarantined)

        # 5. Final confidence filter
        final = [e for e in clean if e.get('confidence', 0) >= config.MIN_CONFIDENCE]
        stats['final_count'] = len(final)

        logger.info(f"Validation complete: {stats['raw_count']} → {stats['final_count']} clean entries")
        return final, stats

    def _is_verified(self, entry: Dict[str, Any]) -> bool:
        status = str(entry.get('status', '')).lower()
        source = str(entry.get('source', '')).lower()
        return status in ('verified', 'approved', 'stored', 'resolved') or source in ('user_feedback', 'admin_verified')

    def _remove_duplicates(self, entries: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        seen: Set[str] = set()
        unique = []
        for e in entries:
            key = self._make_dedup_key(e)
            if key not in seen:
                seen.add(key)
                unique.append(e)
        removed = len(entries) - len(unique)
        if removed:
            logger.info(f"Removed {removed} duplicate entries")
        return unique

    def _make_dedup_key(self, entry: Dict[str, Any]) -> str:
        # Use image_path hash if available, else id+timestamp
        img = entry.get('image_path') or ''
        if img:
            try:
                h = hashlib.md5(img.encode('utf-8')).hexdigest()
            except Exception:
                h = img
        else:
            h = ''
        cls = entry.get('correct_class', '')
        return f"{h}:{cls}:{entry.get('timestamp','')}"

    def _has_valid_class(self, entry: Dict[str, Any]) -> bool:
        cls = entry.get('correct_class', '')
        if not cls:
            return False
        if not self.valid_classes:
            return True
        if cls in self.valid_classes:
            return True
        # Try sanitized variant
        safe = cls.replace('/', '-').replace('\\', '-')
        if safe in self.valid_classes:
            entry['correct_class'] = safe
            return True
        logger.warning(f"Unknown correct_class '{cls}'; skipping entry {entry.get('id')}")
        return False

    def _detect_inconsistencies(self, entries: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """Detect entries where the same image is mapped to multiple classes."""
        image_to_classes: Dict[str, Set[str]] = {}
        for e in entries:
            img = e.get('image_path') or e.get('id')
            if not img:
                continue
            image_to_classes.setdefault(img, set()).add(e.get('correct_class', ''))

        inconsistent_images = {img for img, classes in image_to_classes.items() if len(classes) > 1}
        if inconsistent_images:
            logger.warning(f"Quarantining {len(inconsistent_images)} images with inconsistent labels")

        clean = []
        quarantined = []
        for e in entries:
            img = e.get('image_path') or e.get('id')
            if img in inconsistent_images:
                e['_quarantine_reason'] = 'inconsistent_labels'
                quarantined.append(e)
            else:
                clean.append(e)
        return clean, quarantined


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
    from ingestion import FeedbackIngestion
    ingestion = FeedbackIngestion()
    entries = ingestion.ingest_all()
    validator = FeedbackValidator()
    clean, stats = validator.validate(entries)
    print("Stats:", json.dumps(stats, indent=2))
    print(f"Clean entries: {len(clean)}")
