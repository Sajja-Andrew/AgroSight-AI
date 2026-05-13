"""Tests for pipeline/deployment.py ModelDeployer."""

from pathlib import Path
from unittest.mock import patch
import pytest

from pipeline.deployment import ModelDeployer
from pipeline.versioning import ModelRegistry


class TestModelDeployer:
    """Hot-swap deployment logic."""

    def test_deploy_fails_when_model_missing(self, tmp_path):
        deployer = ModelDeployer(champion_path=tmp_path / 'champion.keras')
        result = deployer.deploy(tmp_path / 'missing.keras', 'v1')
        assert result is False

    def test_deploy_copies_model(self, tmp_path):
        champion = tmp_path / 'champion.keras'
        new_model = tmp_path / 'new.keras'
        new_model.write_bytes(b'model')
        registry = ModelRegistry(registry_path=tmp_path / 'reg.json')
        deployer = ModelDeployer(champion_path=champion, registry=registry)
        result = deployer.deploy(new_model, 'v1')
        assert result is True
        assert champion.exists()
        assert champion.read_bytes() == b'model'

    def test_deploy_restores_backup_on_failure(self, tmp_path):
        champion = tmp_path / 'champion.keras'
        champion.write_bytes(b'old')
        new_model = tmp_path / 'new.keras'
        new_model.write_bytes(b'new')
        registry = ModelRegistry(registry_path=tmp_path / 'reg.json')
        deployer = ModelDeployer(champion_path=champion, registry=registry)

        with patch('pipeline.deployment.shutil.move') as mock_move:
            mock_move.side_effect = RuntimeError('disk full')
            result = deployer.deploy(new_model, 'v1')
            assert result is False
            assert champion.exists()
            assert champion.read_bytes() == b'old'

    def test_rollback_no_previous(self, tmp_path):
        champion = tmp_path / 'champion.keras'
        registry = ModelRegistry(registry_path=tmp_path / 'reg.json')
        deployer = ModelDeployer(champion_path=champion, registry=registry)
        assert deployer.rollback() is False

    def test_rollback_success(self, tmp_path):
        champion = tmp_path / 'champion.keras'
        prev = tmp_path / 'prev.keras'
        prev.write_bytes(b'prev')
        registry = ModelRegistry(registry_path=tmp_path / 'reg.json')
        registry.register('v1', prev, {})
        registry.promote('v1')
        registry.register('v2', tmp_path / 'curr.keras', {})
        registry.promote('v2')

        deployer = ModelDeployer(champion_path=champion, registry=registry)
        assert deployer.rollback() is True
        assert champion.read_bytes() == b'prev'

    def test_get_active_info(self, tmp_path):
        champion = tmp_path / 'champion.keras'
        registry = ModelRegistry(registry_path=tmp_path / 'reg.json')
        registry.register('v1', champion, {})
        registry.promote('v1')
        deployer = ModelDeployer(champion_path=champion, registry=registry)
        info = deployer.get_active_info()
        assert info['version_id'] == 'v1'
