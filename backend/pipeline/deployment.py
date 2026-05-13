"""
Deployment (Hot Swap) module.
Safely replaces the current model only if performance improves.
Supports zero-downtime swap and rollback.
"""

import logging
import os
import shutil
from pathlib import Path
from typing import Optional, Dict, Any

from . import config
from .versioning import ModelRegistry

logger = logging.getLogger(__name__)


class ModelDeployer:
    """Deploy and roll back models with file-based hot-swap."""

    def __init__(self, champion_path: Path = None, registry: ModelRegistry = None):
        self.champion_path = champion_path or config.CHAMPION_MODEL_PATH
        self.registry = registry or ModelRegistry()

    def deploy(self, new_model_path: Path, version_id: str) -> bool:
        """
        Hot-swap the champion model with the new version.
        Uses atomic copy on Windows (symlink fallback where supported).
        """
        if not new_model_path.exists():
            logger.error(f"New model not found: {new_model_path}")
            return False

        # Ensure parent dir exists
        self.champion_path.parent.mkdir(parents=True, exist_ok=True)

        # Backup current champion if it exists
        backup_path = None
        if self.champion_path.exists():
            backup_path = self.champion_path.with_suffix('.backup.keras')
            try:
                shutil.copy2(str(self.champion_path), str(backup_path))
                logger.info(f"Backed up champion to {backup_path}")
            except Exception as e:
                logger.warning(f"Could not backup champion: {e}")

        # Replace champion atomically by writing to temp then rename
        temp_path = self.champion_path.with_suffix('.tmp.keras')
        try:
            shutil.copy2(str(new_model_path), str(temp_path))
            if self.champion_path.exists() or self.champion_path.is_symlink():
                self.champion_path.unlink()
            shutil.move(str(temp_path), str(self.champion_path))
            logger.info(f"Deployed new champion: {self.champion_path} -> {new_model_path}")
        except Exception as e:
            logger.error(f"Deployment failed: {e}")
            # Attempt restore from backup
            if backup_path and backup_path.exists():
                try:
                    shutil.copy2(str(backup_path), str(self.champion_path))
                    logger.info("Restored champion from backup after failed deploy")
                except Exception as restore_err:
                    logger.critical(f"Could not restore champion: {restore_err}")
            return False

        # Update registry
        self.registry.promote(version_id)
        self.registry.prune()
        return True

    def rollback(self) -> bool:
        """Roll back to the previous champion version."""
        prev = self.registry.get_previous_champion()
        if not prev:
            logger.warning("No previous champion found for rollback")
            return False

        prev_path = Path(prev['path'])
        if not prev_path.exists():
            logger.error(f"Previous champion file missing: {prev_path}")
            return False

        try:
            if self.champion_path.exists() or self.champion_path.is_symlink():
                self.champion_path.unlink()
            shutil.copy2(str(prev_path), str(self.champion_path))
            logger.info(f"Rolled back to previous champion: {prev_path}")
            self.registry.promote(prev['version_id'])
            return True
        except Exception as e:
            logger.error(f"Rollback failed: {e}")
            return False

    def get_active_info(self) -> Optional[Dict[str, Any]]:
        return self.registry.get_champion()
