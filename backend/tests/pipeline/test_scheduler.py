"""Tests for pipeline/scheduler.py RetrainingScheduler."""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

from pipeline.scheduler import RetrainingScheduler


class TestSchedulerInit:
    """Basic scheduler setup."""

    def test_is_running_false_when_no_lock(self, tmp_path, monkeypatch):
        monkeypatch.setattr('pipeline.scheduler.config.PIPELINE_LOCK_FILE', tmp_path / 'lock')
        sched = RetrainingScheduler()
        assert sched.is_running() is False

    def test_is_running_true_when_lock_exists(self, tmp_path, monkeypatch):
        lock = tmp_path / 'lock'
        lock.write_text('locked')
        monkeypatch.setattr('pipeline.scheduler.config.PIPELINE_LOCK_FILE', lock)
        sched = RetrainingScheduler()
        assert sched.is_running() is True


class TestAcquireReleaseLock:
    """Lock file management."""

    def test_acquire_lock_creates_file(self, tmp_path, monkeypatch):
        lock = tmp_path / 'subdir' / 'lock'
        monkeypatch.setattr('pipeline.scheduler.config.PIPELINE_LOCK_FILE', lock)
        sched = RetrainingScheduler()
        sched._acquire_lock()
        assert lock.exists()

    def test_release_lock_removes_file(self, tmp_path, monkeypatch):
        lock = tmp_path / 'lock'
        lock.write_text('locked')
        monkeypatch.setattr('pipeline.scheduler.config.PIPELINE_LOCK_FILE', lock)
        sched = RetrainingScheduler()
        sched._release_lock()
        assert not lock.exists()


class TestStart:
    """Scheduler start behavior."""

    def test_returns_false_when_aps_not_available(self, monkeypatch):
        monkeypatch.setattr('pipeline.scheduler.APS_AVAILABLE', False)
        sched = RetrainingScheduler()
        assert sched.start() is False

    def test_returns_false_when_schedule_off(self, monkeypatch):
        monkeypatch.setattr('pipeline.scheduler.APS_AVAILABLE', True)
        monkeypatch.setattr('pipeline.scheduler.config.RETRAIN_SCHEDULE', 'off')
        sched = RetrainingScheduler()
        assert sched.start() is False

    def test_starts_weekly_schedule(self, monkeypatch):
        monkeypatch.setattr('pipeline.scheduler.APS_AVAILABLE', True)
        monkeypatch.setattr('pipeline.scheduler.config.RETRAIN_SCHEDULE', 'weekly')
        monkeypatch.setattr('pipeline.scheduler.config.RETRAIN_DAY_OF_WEEK', 0)
        monkeypatch.setattr('pipeline.scheduler.config.RETRAIN_HOUR', 2)
        monkeypatch.setattr('pipeline.scheduler.config.RETRAIN_MINUTE', 0)

        mock_scheduler_cls = MagicMock()
        mock_scheduler = MagicMock()
        mock_scheduler_cls.return_value = mock_scheduler
        monkeypatch.setattr('pipeline.scheduler.BackgroundScheduler', mock_scheduler_cls)

        sched = RetrainingScheduler(job_func=lambda: None)
        assert sched.start() is True
        mock_scheduler.add_job.assert_called_once()
        call_args = mock_scheduler.add_job.call_args[0]
        assert 'cron' in call_args

    def test_unknown_schedule_returns_false(self, monkeypatch):
        monkeypatch.setattr('pipeline.scheduler.APS_AVAILABLE', True)
        monkeypatch.setattr('pipeline.scheduler.config.RETRAIN_SCHEDULE', 'daily')
        sched = RetrainingScheduler()
        assert sched.start() is False


class TestRunJob:
    """Job execution."""

    def test_skips_when_already_running(self, tmp_path, monkeypatch):
        lock = tmp_path / 'lock'
        lock.write_text('locked')
        monkeypatch.setattr('pipeline.scheduler.config.PIPELINE_LOCK_FILE', lock)
        monkeypatch.setattr('pipeline.scheduler.APS_AVAILABLE', True)

        mock_job = MagicMock()
        sched = RetrainingScheduler(job_func=mock_job)
        sched._run_job()
        mock_job.assert_not_called()

    def test_executes_job_when_not_running(self, tmp_path, monkeypatch):
        monkeypatch.setattr('pipeline.scheduler.config.PIPELINE_LOCK_FILE', tmp_path / 'lock')
        monkeypatch.setattr('pipeline.scheduler.APS_AVAILABLE', True)

        mock_job = MagicMock()
        sched = RetrainingScheduler(job_func=mock_job)
        sched._run_job()
        mock_job.assert_called_once()

    def test_releases_lock_on_exception(self, tmp_path, monkeypatch):
        monkeypatch.setattr('pipeline.scheduler.config.PIPELINE_LOCK_FILE', tmp_path / 'lock')
        monkeypatch.setattr('pipeline.scheduler.APS_AVAILABLE', True)

        mock_job = MagicMock(side_effect=RuntimeError('boom'))
        sched = RetrainingScheduler(job_func=mock_job)
        sched._run_job()
        mock_job.assert_called_once()
        assert not sched.is_running()  # lock released in finally


class TestTriggerNow:
    """Manual trigger."""

    def test_returns_false_when_no_job_func(self):
        sched = RetrainingScheduler()
        assert sched.trigger_now() is False

    def test_runs_job_immediately(self, tmp_path, monkeypatch):
        monkeypatch.setattr('pipeline.scheduler.config.PIPELINE_LOCK_FILE', tmp_path / 'lock')
        mock_job = MagicMock()
        sched = RetrainingScheduler(job_func=mock_job)
        assert sched.trigger_now() is True
        mock_job.assert_called_once()
