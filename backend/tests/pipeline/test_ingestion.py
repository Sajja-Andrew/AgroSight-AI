"""Tests for pipeline/ingestion.py FeedbackIngestion."""

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock
import pytest

from pipeline.ingestion import FeedbackIngestion


class TestIngestFeedbackJson:
    """Reading backend/data/feedback.json."""

    def test_ingests_list_of_entries(self, tmp_path, monkeypatch):
        feedback_file = tmp_path / 'feedback.json'
        feedback_file.write_text(json.dumps([
            {'id': '1', 'predicted_class': 'A', 'correct_class': 'B'},
            {'id': '2', 'predicted_class': 'C', 'correct_class': 'D'},
        ]))
        monkeypatch.setattr('pipeline.ingestion.config.FEEDBACK_JSON_PATH', feedback_file)

        ingestion = FeedbackIngestion()
        ingestion._ingest_feedback_json()
        entries = ingestion.entries
        assert len(entries) == 2
        assert entries[0]['predicted_class'] == 'A'

    def test_skips_non_dict_items(self, tmp_path, monkeypatch):
        feedback_file = tmp_path / 'feedback.json'
        feedback_file.write_text(json.dumps([
            {'id': '1', 'predicted_class': 'A', 'correct_class': 'B'},
            'bad',
            None
        ]))
        monkeypatch.setattr('pipeline.ingestion.config.FEEDBACK_JSON_PATH', feedback_file)

        ingestion = FeedbackIngestion()
        ingestion._ingest_feedback_json()
        entries = ingestion.entries
        assert len(entries) == 1

    def test_skips_when_file_missing(self, tmp_path, monkeypatch):
        missing = tmp_path / 'missing.json'
        monkeypatch.setattr('pipeline.ingestion.config.FEEDBACK_JSON_PATH', missing)

        ingestion = FeedbackIngestion()
        ingestion._ingest_feedback_json()
        entries = ingestion.entries
        assert entries == []

    def test_skips_malformed_json(self, tmp_path, monkeypatch):
        feedback_file = tmp_path / 'feedback.json'
        feedback_file.write_text('not json')
        monkeypatch.setattr('pipeline.ingestion.config.FEEDBACK_JSON_PATH', feedback_file)

        ingestion = FeedbackIngestion()
        ingestion._ingest_feedback_json()
        entries = ingestion.entries
        assert entries == []

    def test_skips_non_list_root(self, tmp_path, monkeypatch):
        feedback_file = tmp_path / 'feedback.json'
        feedback_file.write_text(json.dumps({'entries': []}))
        monkeypatch.setattr('pipeline.ingestion.config.FEEDBACK_JSON_PATH', feedback_file)

        ingestion = FeedbackIngestion()
        ingestion._ingest_feedback_json()
        entries = ingestion.entries
        assert entries == []


class TestIngestFeedbackLogJson:
    """Reading backend/feedback/feedback_log.json."""

    def test_ingests_entries_key(self, tmp_path, monkeypatch):
        log_file = tmp_path / 'feedback_log.json'
        log_file.write_text(json.dumps({
            'entries': [
                {'id': '1', 'predicted_class': 'A', 'correct_class': 'B', 'file_path': 'img1.jpg'},
            ]
        }))
        monkeypatch.setattr('pipeline.ingestion.config.FEEDBACK_LOG_PATH', log_file)

        ingestion = FeedbackIngestion()
        ingestion._ingest_feedback_log_json()
        entries = ingestion.entries
        assert len(entries) == 1
        assert entries[0]['image_path'] == 'img1.jpg'

    def test_ingests_flat_list(self, tmp_path, monkeypatch):
        log_file = tmp_path / 'feedback_log.json'
        log_file.write_text(json.dumps([
            {'id': '1', 'predicted_class': 'A', 'correct_class': 'B'},
        ]))
        monkeypatch.setattr('pipeline.ingestion.config.FEEDBACK_LOG_PATH', log_file)

        ingestion = FeedbackIngestion()
        ingestion._ingest_feedback_log_json()
        entries = ingestion.entries
        assert len(entries) == 1

    def test_skips_when_file_missing(self, tmp_path, monkeypatch):
        monkeypatch.setattr('pipeline.ingestion.config.FEEDBACK_LOG_PATH', tmp_path / 'missing.json')
        ingestion = FeedbackIngestion()
        ingestion._ingest_feedback_log_json()
        entries = ingestion.entries
        assert entries == []


class TestNormalize:
    """Entry normalization."""

    def test_normalizes_minimal_entry(self):
        ingestion = FeedbackIngestion()
        result = ingestion._normalize({'predicted_class': 'A', 'correct_class': 'B'})
        assert result['predicted_class'] == 'A'
        assert result['correct_class'] == 'B'
        assert result['source'] == 'user_feedback'
        assert result['status'] == 'verified'

    def test_returns_none_when_no_classes(self):
        ingestion = FeedbackIngestion()
        assert ingestion._normalize({'id': '1'}) is None

    def test_maps_file_path_to_image_path(self):
        ingestion = FeedbackIngestion()
        result = ingestion._normalize({'predicted_class': 'A', 'correct_class': 'B', 'file_path': 'img.jpg'})
        assert result['image_path'] == 'img.jpg'


class TestIngestAll:
    """End-to-end ingestion."""

    def test_ingest_all_combines_sources(self, tmp_path, monkeypatch):
        fb = tmp_path / 'feedback.json'
        fb.write_text(json.dumps([{'id': '1', 'predicted_class': 'A', 'correct_class': 'B'}]))
        log = tmp_path / 'feedback_log.json'
        log.write_text(json.dumps([{'id': '2', 'predicted_class': 'C', 'correct_class': 'D'}]))

        monkeypatch.setattr('pipeline.ingestion.config.FEEDBACK_JSON_PATH', fb)
        monkeypatch.setattr('pipeline.ingestion.config.FEEDBACK_LOG_PATH', log)

        ingestion = FeedbackIngestion()
        entries = ingestion.ingest_all()
        assert len(entries) == 2
