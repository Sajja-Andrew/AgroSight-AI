"""
Unit tests for pipeline.versioning.ModelRegistry.
"""

import json
import tempfile
from pathlib import Path

from pipeline.versioning import ModelRegistry


class TestModelRegistry:
    """Test the lightweight JSON-based model registry."""

    def setup_method(self):
        self.tmp_dir = Path(tempfile.mkdtemp())
        self.registry_path = self.tmp_dir / 'registry.json'
        self.registry = ModelRegistry(registry_path=self.registry_path)

    def teardown_method(self):
        for f in self.tmp_dir.iterdir():
            f.unlink()
        self.tmp_dir.rmdir()

    def test_register_new_version(self):
        self.registry.register('v1', Path('/models/v1.keras'), {'accuracy': 0.9}, status='champion')
        versions = self.registry.list_versions()
        assert len(versions) == 1
        assert versions[0]['version_id'] == 'v1'
        assert versions[0]['status'] == 'champion'

    def test_promote_challenger(self):
        self.registry.register('v1', Path('/models/v1.keras'), {'accuracy': 0.9}, status='champion')
        self.registry.register('v2', Path('/models/v2.keras'), {'accuracy': 0.95}, status='challenger')

        promoted = self.registry.promote('v2')
        assert promoted is not None
        assert promoted['status'] == 'champion'

        champion = self.registry.get_champion()
        assert champion['version_id'] == 'v2'

        previous = [v for v in self.registry.list_versions() if v['version_id'] == 'v1'][0]
        assert previous['status'] == 'archived'

    def test_get_previous_champion(self):
        self.registry.register('v1', Path('/models/v1.keras'), {'accuracy': 0.9}, status='archived')
        self.registry.register('v2', Path('/models/v2.keras'), {'accuracy': 0.95}, status='champion')

        prev = self.registry.get_previous_champion()
        assert prev is not None
        assert prev['version_id'] == 'v1'

    def test_prune_keeps_champion(self):
        self.registry.register('v1', Path('/models/v1.keras'), {'accuracy': 0.9}, status='archived')
        self.registry.register('v2', Path('/models/v2.keras'), {'accuracy': 0.95}, status='champion')
        self.registry.register('v3', Path('/models/v3.keras'), {'accuracy': 0.96}, status='challenger')

        self.registry.prune(keep=2)
        versions = self.registry.list_versions()
        assert len(versions) == 3
        # Champion and active should never be deleted
        assert self.registry.get_champion()['version_id'] == 'v2'

    def test_registry_file_created(self):
        assert self.registry_path.exists()
        data = json.loads(self.registry_path.read_text())
        assert 'versions' in data
