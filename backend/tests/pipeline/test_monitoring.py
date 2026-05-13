"""Tests for pipeline/monitoring.py PipelineLogger."""

import json
from pathlib import Path
import pytest

from pipeline.monitoring import PipelineLogger


class TestPipelineLogger:
    """Structured JSONL logging."""

    def test_start_run_creates_file(self, tmp_path):
        logger = PipelineLogger(log_dir=tmp_path)
        run_id = logger.start_run()
        assert logger.current_log_file.exists()
        assert run_id is not None

    def test_log_stage_appends(self, tmp_path):
        logger = PipelineLogger(log_dir=tmp_path)
        logger.start_run('run1')
        logger.log_stage('ingestion', {'count': 5})
        lines = logger.current_log_file.read_text().strip().split('\n')
        assert len(lines) == 2
        assert json.loads(lines[1])['stage'] == 'ingestion'

    def test_log_metrics(self, tmp_path):
        logger = PipelineLogger(log_dir=tmp_path)
        logger.start_run('run2')
        logger.log_metrics({'accuracy': 0.9})
        lines = logger.current_log_file.read_text().strip().split('\n')
        assert json.loads(lines[1])['metrics']['accuracy'] == 0.9

    def test_log_decision(self, tmp_path):
        logger = PipelineLogger(log_dir=tmp_path)
        logger.start_run('run3')
        logger.log_decision('promote', 'accuracy improved', {'delta': 0.02})
        lines = logger.current_log_file.read_text().strip().split('\n')
        data = json.loads(lines[1])
        assert data['decision'] == 'promote'
        assert data['metadata']['delta'] == 0.02

    def test_log_feedback_distribution(self, tmp_path):
        logger = PipelineLogger(log_dir=tmp_path)
        logger.start_run('run4')
        logger.log_feedback_distribution([
            {'correct_class': 'A'},
            {'correct_class': 'B'},
            {'correct_class': 'A'},
        ])
        lines = logger.current_log_file.read_text().strip().split('\n')
        dist = json.loads(lines[1])['distribution']
        assert dist['A'] == 2
        assert dist['B'] == 1

    def test_end_run(self, tmp_path):
        logger = PipelineLogger(log_dir=tmp_path)
        logger.start_run('run5')
        logger.end_run(status='success')
        lines = logger.current_log_file.read_text().strip().split('\n')
        assert json.loads(lines[1])['status'] == 'success'

    def test_end_run_with_error(self, tmp_path):
        logger = PipelineLogger(log_dir=tmp_path)
        logger.start_run('run6')
        logger.end_run(status='failed', error='OOM')
        lines = logger.current_log_file.read_text().strip().split('\n')
        assert json.loads(lines[1])['error'] == 'OOM'

    def test_write_without_start_run_auto_starts(self, tmp_path):
        logger = PipelineLogger(log_dir=tmp_path)
        logger.log_metrics({'f1': 0.8})
        assert logger.current_log_file.exists()
