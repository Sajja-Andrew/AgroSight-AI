"""
Model Versioning module.
Maintains a lightweight JSON-based model registry with champion/challenger/archived states.
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional

from . import config

logger = logging.getLogger(__name__)


class ModelRegistry:
    """Simple file-based model registry."""

    def __init__(self, registry_path: Path = None):
        self.registry_path = registry_path or config.MODEL_REGISTRY_PATH
        self._ensure_registry()

    def _ensure_registry(self):
        if not self.registry_path.exists():
            self.registry_path.parent.mkdir(parents=True, exist_ok=True)
            self._write({'versions': [], 'active_version': None})

    def _read(self) -> Dict[str, Any]:
        try:
            with open(self.registry_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error reading registry: {e}; returning empty")
            return {'versions': [], 'active_version': None}

    def _write(self, data: Dict[str, Any]):
        with open(self.registry_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2)

    def register(self, version_id: str, model_path: Path, metrics: Dict[str, Any],
                 status: str = 'challenger') -> Dict[str, Any]:
        """Register a newly trained model version."""
        data = self._read()
        entry = {
            'version_id': version_id,
            'path': str(model_path),
            'metrics': metrics,
            'status': status,
            'created_at': datetime.now().isoformat(),
        }
        # Remove existing entry with same version_id if present
        data['versions'] = [v for v in data['versions'] if v['version_id'] != version_id]
        data['versions'].append(entry)
        self._write(data)
        logger.info(f"Registered model version {version_id} as {status}")
        return entry

    def promote(self, version_id: str) -> Optional[Dict[str, Any]]:
        """Promote a challenger to champion and archive the old champion."""
        data = self._read()
        promoted = None
        for v in data['versions']:
            if v['version_id'] == version_id:
                v['status'] = 'champion'
                promoted = v
            elif v['status'] == 'champion':
                v['status'] = 'archived'
        if promoted:
            data['active_version'] = version_id
            self._write(data)
            logger.info(f"Promoted {version_id} to champion")
        else:
            logger.warning(f"Version {version_id} not found; cannot promote")
        return promoted

    def get_champion(self) -> Optional[Dict[str, Any]]:
        data = self._read()
        for v in data['versions']:
            if v['status'] == 'champion':
                return v
        # Fallback to active_version
        active = data.get('active_version')
        if active:
            for v in data['versions']:
                if v['version_id'] == active:
                    return v
        return None

    def get_previous_champion(self) -> Optional[Dict[str, Any]]:
        """Return the most recent archived champion for rollback."""
        data = self._read()
        archived = [v for v in data['versions'] if v['status'] == 'archived']
        if not archived:
            return None
        archived.sort(key=lambda x: x.get('created_at', ''), reverse=True)
        return archived[0]

    def list_versions(self) -> List[Dict[str, Any]]:
        return self._read().get('versions', [])

    def prune(self, keep: int = None):
        """Remove old archived model files, keeping the last N champions/challengers."""
        keep = keep or config.KEEP_VERSIONS
        data = self._read()
        # Never delete champion or active
        protected = {data.get('active_version')}
        for v in data['versions']:
            if v['status'] == 'champion':
                protected.add(v['version_id'])

        # Sort all by created_at desc
        all_sorted = sorted(data['versions'], key=lambda x: x.get('created_at', ''), reverse=True)
        kept = []
        removed = []
        for v in all_sorted:
            if v['version_id'] in protected or len(kept) < keep:
                kept.append(v)
            else:
                removed.append(v)
                # Delete file
                try:
                    p = Path(v['path'])
                    if p.exists():
                        p.unlink()
                        logger.info(f"Pruned old model file: {p}")
                except Exception as e:
                    logger.warning(f"Could not delete {v['path']}: {e}")
                v['status'] = 'deleted'

        data['versions'] = kept + removed
        self._write(data)
