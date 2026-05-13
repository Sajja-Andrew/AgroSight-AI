"""
Scheduling module.
Uses APScheduler to run periodic retraining jobs (weekly or monthly).
Singleton-safe via a lock file.
"""

import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Callable

from . import config

logger = logging.getLogger(__name__)

# Optional APScheduler import; fail gracefully if missing
try:
    from apscheduler.schedulers.background import BackgroundScheduler
    APS_AVAILABLE = True
except ImportError:
    APS_AVAILABLE = False
    BackgroundScheduler = None


class RetrainingScheduler:
    """Wrapper around APScheduler for periodic model retraining."""

    def __init__(self, job_func: Callable = None):
        self.job_func = job_func
        self.scheduler = None
        self._lock_file = config.PIPELINE_LOCK_FILE

    def is_running(self) -> bool:
        return self._lock_file.exists()

    def _acquire_lock(self):
        self._lock_file.parent.mkdir(parents=True, exist_ok=True)
        self._lock_file.write_text(datetime.now().isoformat())

    def _release_lock(self):
        if self._lock_file.exists():
            self._lock_file.unlink()

    def start(self, schedule: str = None):
        if not APS_AVAILABLE:
            logger.error("APScheduler not installed. Install it or set RETRAIN_SCHEDULE=off")
            return False

        schedule = schedule or config.RETRAIN_SCHEDULE
        if schedule.lower() == 'off':
            logger.info("Retraining scheduler is disabled (RETRAIN_SCHEDULE=off)")
            return False

        self.scheduler = BackgroundScheduler()
        if schedule.lower() == 'weekly':
            self.scheduler.add_job(
                self._run_job,
                'cron',
                day_of_week=config.RETRAIN_DAY_OF_WEEK,
                hour=config.RETRAIN_HOUR,
                minute=config.RETRAIN_MINUTE,
                id='weekly_retrain',
                replace_existing=True
            )
            logger.info(
                f"Scheduled weekly retraining: day={config.RETRAIN_DAY_OF_WEEK}, "
                f"time={config.RETRAIN_HOUR:02d}:{config.RETRAIN_MINUTE:02d}"
            )
        elif schedule.lower() == 'monthly':
            self.scheduler.add_job(
                self._run_job,
                'cron',
                day='1',
                hour=config.RETRAIN_HOUR,
                minute=config.RETRAIN_MINUTE,
                id='monthly_retrain',
                replace_existing=True
            )
            logger.info(
                f"Scheduled monthly retraining: day=1, "
                f"time={config.RETRAIN_HOUR:02d}:{config.RETRAIN_MINUTE:02d}"
            )
        else:
            logger.error(f"Unknown schedule: {schedule}. Use weekly, monthly, or off.")
            return False

        self.scheduler.start()
        return True

    def stop(self):
        if self.scheduler:
            self.scheduler.shutdown(wait=False)
            logger.info("Scheduler stopped")

    def trigger_now(self) -> bool:
        """Manually trigger a retraining run."""
        if not self.job_func:
            logger.error("No job function configured for scheduler")
            return False
        self._run_job()
        return True

    def _run_job(self):
        if self.is_running():
            logger.warning("Pipeline already running; skipping scheduled job")
            return
        if not self.job_func:
            logger.error("No job function configured")
            return
        try:
            self._acquire_lock()
            logger.info("Scheduled retraining job started")
            self.job_func()
            logger.info("Scheduled retraining job completed")
        except Exception as e:
            logger.error(f"Scheduled retraining job failed: {e}")
        finally:
            self._release_lock()
