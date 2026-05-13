"""
Data Ingestion module.
Reads and parses feedback from JSON files, DB (optional), and feedback image logs.
Handles malformed or missing data gracefully.
"""

import json
import logging
import os
from pathlib import Path
from typing import List, Dict, Any, Optional

from . import config

logger = logging.getLogger(__name__)


class FeedbackIngestion:
    """Ingest feedback from multiple sources and normalize to a common schema."""

    SCHEMA_KEYS = {'id', 'predicted_class', 'correct_class', 'confidence', 'timestamp', 'source', 'status', 'image_path'}

    def __init__(self):
        self.entries: List[Dict[str, Any]] = []

    def ingest_all(self, include_db: bool = False, app=None) -> List[Dict[str, Any]]:
        """Ingest from all available sources."""
        self.entries = []
        self._ingest_feedback_json()
        self._ingest_feedback_log_json()
        if include_db and app is not None:
            self._ingest_from_database(app)
        logger.info(f"Ingested {len(self.entries)} total feedback entries")
        return self.entries

    def _ingest_feedback_json(self):
        """Read backend/data/feedback.json."""
        path = config.FEEDBACK_JSON_PATH
        if not path.exists():
            logger.warning(f"feedback.json not found at {path}")
            return
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            if not isinstance(data, list):
                logger.warning("feedback.json root is not a list; skipping")
                return
            for idx, item in enumerate(data):
                if not isinstance(item, dict):
                    logger.warning(f"Skipping non-dict item at index {idx}")
                    continue
                entry = self._normalize(item)
                if entry:
                    self.entries.append(entry)
            logger.info(f"Ingested {len(self.entries)} entries from feedback.json")
        except json.JSONDecodeError as e:
            logger.error(f"Malformed JSON in feedback.json: {e}")
        except Exception as e:
            logger.error(f"Error reading feedback.json: {e}")

    def _ingest_feedback_log_json(self):
        """Read backend/feedback/feedback_log.json (image-based corrections)."""
        path = config.FEEDBACK_LOG_PATH
        if not path.exists():
            logger.warning(f"feedback_log.json not found at {path}")
            return
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            if isinstance(data, list):
                items = data
            elif isinstance(data, dict) and 'entries' in data:
                items = data['entries']
            else:
                logger.warning("feedback_log.json has unexpected shape; skipping")
                return
            count = 0
            for idx, item in enumerate(items):
                if not isinstance(item, dict):
                    continue
                entry = self._normalize(item)
                if entry:
                    # Ensure image_path is present
                    if not entry.get('image_path') and item.get('file_path'):
                        entry['image_path'] = item['file_path']
                    self.entries.append(entry)
                    count += 1
            logger.info(f"Ingested {count} entries from feedback_log.json")
        except json.JSONDecodeError as e:
            logger.error(f"Malformed JSON in feedback_log.json: {e}")
        except Exception as e:
            logger.error(f"Error reading feedback_log.json: {e}")

    def _ingest_from_database(self, app):
        """Optionally read from SQLite via Flask app context."""
        try:
            with app.app_context():
                from database import Feedback
                rows = Feedback.query.order_by(Feedback.created_at.desc()).all()
                count = 0
                for row in rows:
                    entry = {
                        'id': f"db_{row.id}",
                        'predicted_class': row.predicted_class or '',
                        'correct_class': row.correct_class or '',
                        'confidence': row.confidence or 0.0,
                        'timestamp': row.created_at.isoformat() if row.created_at else '',
                        'source': 'user_feedback',
                        'status': 'verified',
                        'image_path': row.image_path,
                    }
                    self.entries.append(entry)
                    count += 1
                logger.info(f"Ingested {count} entries from database")
        except Exception as e:
            logger.error(f"Error ingesting from database: {e}")

    def _normalize(self, raw: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Normalize a raw feedback entry to the common schema."""
        if not raw.get('predicted_class') and not raw.get('correct_class'):
            return None
        entry = {
            'id': raw.get('id') or raw.get('feedback_id') or '',
            'predicted_class': str(raw.get('predicted_class', '')).strip(),
            'correct_class': str(raw.get('correct_class', '')).strip(),
            'confidence': self._parse_float(raw.get('confidence'), 0.0),
            'timestamp': raw.get('timestamp') or raw.get('created_at') or '',
            'source': raw.get('source') or 'user_feedback',
            'status': raw.get('status') or 'verified',
            'image_path': raw.get('image_path') or raw.get('file_path') or raw.get('image_id') or None,
        }
        return entry

    @staticmethod
    def _parse_float(value, default):
        try:
            return float(value) if value is not None else default
        except (ValueError, TypeError):
            return default

    def get_entries(self) -> List[Dict[str, Any]]:
        return self.entries


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
    ingestion = FeedbackIngestion()
    entries = ingestion.ingest_all()
    print(f"Total entries: {len(entries)}")
    for e in entries[:3]:
        print(e)
