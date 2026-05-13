"""
Logging and Monitoring module.
Writes structured JSONL logs per retraining cycle.
Tracks model performance over time and feedback class distributions.
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List

from . import config

logger = logging.getLogger(__name__)


class PipelineLogger:
    """Structured logger for retraining pipeline runs."""

    def __init__(self, log_dir: Path = None):
        self.log_dir = Path(log_dir) if log_dir else config.RETRAIN_LOG_DIR
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.current_log_file: Path = None

    def start_run(self, run_id: str = None) -> str:
        run_id = run_id or datetime.now().strftime('%Y%m%d_%H%M%S')
        self.current_log_file = self.log_dir / f'retrain_{run_id}.jsonl'
        self._write({
            'event': 'run_start',
            'run_id': run_id,
            'timestamp': datetime.now().isoformat(),
        })
        return run_id

    def log_stage(self, stage: str, details: Dict[str, Any]):
        self._write({
            'event': 'stage',
            'stage': stage,
            'timestamp': datetime.now().isoformat(),
            'details': details,
        })

    def log_metrics(self, metrics: Dict[str, Any]):
        self._write({
            'event': 'metrics',
            'timestamp': datetime.now().isoformat(),
            'metrics': metrics,
        })

    def log_decision(self, decision: str, reason: str, metadata: Dict[str, Any] = None):
        self._write({
            'event': 'decision',
            'decision': decision,
            'reason': reason,
            'timestamp': datetime.now().isoformat(),
            'metadata': metadata or {},
        })

    def log_feedback_distribution(self, entries: List[Dict[str, Any]]):
        dist: Dict[str, int] = {}
        for e in entries:
            cls = e.get('correct_class', 'unknown')
            dist[cls] = dist.get(cls, 0) + 1
        self._write({
            'event': 'feedback_distribution',
            'timestamp': datetime.now().isoformat(),
            'distribution': dist,
        })

    def end_run(self, status: str = 'completed', error: str = None):
        payload = {
            'event': 'run_end',
            'status': status,
            'timestamp': datetime.now().isoformat(),
        }
        if error:
            payload['error'] = error
        self._write(payload)

    def _write(self, record: Dict[str, Any]):
        if not self.current_log_file:
            self.start_run()
        try:
            with open(self.current_log_file, 'a', encoding='utf-8') as f:
                f.write(json.dumps(record, default=str) + '\n')
        except Exception as e:
            logger.warning(f"Could not write to pipeline log: {e}")
