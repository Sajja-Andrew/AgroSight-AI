"""
Unit tests for pipeline.deployment.ModelDeployer.
"""

import shutil
import tempfile
from pathlib import Path

from pipeline.deployment import ModelDeployer
from pipeline.versioning import ModelRegistry


class TestModelDeployer:
    """Test model hot-swap and rollback without touching production paths."""

    def setup_method(self):
        self.tmp_dir = Path(tempfile.mkdtemp())
        self.champion_path = self.tmp_dir / 'best_model_finetuned.keras'
        # Create a fake champion file
        self.champion_path.write_bytes(b'old_model')
        self.registry = ModelRegistry(registry_path=self.tmp_dir / 'registry.json')
        self.deployer = ModelDeployer(champion_path=self.champion_path, registry=self.registry)

    def teardown_method(self):
        shutil.rmtree(self.tmp_dir)

    def test_deploy_replaces_champion(self):
        new_model = self.tmp_dir / 'new_model.keras'
        new_model.write_bytes(b'new_model')

        self.registry.register('v_old', self.champion_path, {'accuracy': 0.9}, status='champion')
        self.registry.register('v_new', new_model, {'accuracy': 0.95}, status='challenger')

        ok = self.deployer.deploy(new_model, 'v_new')
        assert ok is True
        assert self.champion_path.read_bytes() == b'new_model'
        assert self.registry.get_champion()['version_id'] == 'v_new'

    def test_deploy_missing_model_fails(self):
        missing = self.tmp_dir / 'missing.keras'
        ok = self.deployer.deploy(missing, 'v_missing')
        assert ok is False

    def test_rollback_restores_previous(self):
        # Keep the old model at a separate path (as it would be in production)
        old_model_path = self.tmp_dir / 'v_old.keras'
        shutil.copy2(self.champion_path, old_model_path)

        new_model = self.tmp_dir / 'new_model.keras'
        new_model.write_bytes(b'new_model')

        self.registry.register('v_old', old_model_path, {'accuracy': 0.9}, status='archived')
        self.registry.register('v_new', new_model, {'accuracy': 0.95}, status='champion')
        # Actually replace the champion file
        self.champion_path.write_bytes(b'new_model')

        ok = self.deployer.rollback()
        assert ok is True
        assert self.champion_path.read_bytes() == b'old_model'
        assert self.registry.get_champion()['version_id'] == 'v_old'
