"""Tests for pipeline/versioning.py ModelRegistry."""

import json
from pathlib import Path
import pytest

from pipeline.versioning import ModelRegistry


class TestModelRegistry:
    """File-based model registry."""

    def test_ensures_registry_exists(self, tmp_path):
        reg_file = tmp_path / 'registry.json'
        registry = ModelRegistry(registry_path=reg_file)
        assert reg_file.exists()
        data = json.loads(reg_file.read_text())
        assert data['versions'] == []
        assert data['active_version'] is None

    def test_register_adds_version(self, tmp_path):
        reg_file = tmp_path / 'registry.json'
        registry = ModelRegistry(registry_path=reg_file)
        entry = registry.register('v1', tmp_path / 'model.keras', {'accuracy': 0.9})
        assert entry['version_id'] == 'v1'
        assert entry['status'] == 'challenger'

    def test_register_removes_duplicate_version_id(self, tmp_path):
        reg_file = tmp_path / 'registry.json'
        registry = ModelRegistry(registry_path=reg_file)
        registry.register('v1', tmp_path / 'a.keras', {'accuracy': 0.8})
        registry.register('v1', tmp_path / 'b.keras', {'accuracy': 0.9})
        versions = registry.list_versions()
        assert len(versions) == 1
        assert versions[0]['metrics']['accuracy'] == 0.9

    def test_promote_to_champion(self, tmp_path):
        reg_file = tmp_path / 'registry.json'
        registry = ModelRegistry(registry_path=reg_file)
        registry.register('v1', tmp_path / 'm1.keras', {'accuracy': 0.9})
        promoted = registry.promote('v1')
        assert promoted['status'] == 'champion'

    def test_promote_archives_old_champion(self, tmp_path):
        reg_file = tmp_path / 'registry.json'
        registry = ModelRegistry(registry_path=reg_file)
        registry.register('v1', tmp_path / 'm1.keras', {})
        registry.promote('v1')
        registry.register('v2', tmp_path / 'm2.keras', {})
        registry.promote('v2')
        versions = {v['version_id']: v['status'] for v in registry.list_versions()}
        assert versions['v1'] == 'archived'
        assert versions['v2'] == 'champion'

    def test_get_champion_returns_none_when_empty(self, tmp_path):
        reg_file = tmp_path / 'registry.json'
        registry = ModelRegistry(registry_path=reg_file)
        assert registry.get_champion() is None

    def test_get_previous_champion(self, tmp_path):
        reg_file = tmp_path / 'registry.json'
        registry = ModelRegistry(registry_path=reg_file)
        registry.register('v1', tmp_path / 'm1.keras', {})
        registry.promote('v1')
        registry.register('v2', tmp_path / 'm2.keras', {})
        registry.promote('v2')
        prev = registry.get_previous_champion()
        assert prev['version_id'] == 'v1'

    def test_get_previous_champion_none_when_no_archived(self, tmp_path):
        reg_file = tmp_path / 'registry.json'
        registry = ModelRegistry(registry_path=reg_file)
        assert registry.get_previous_champion() is None

    def test_list_versions(self, tmp_path):
        reg_file = tmp_path / 'registry.json'
        registry = ModelRegistry(registry_path=reg_file)
        registry.register('v1', tmp_path / 'm1.keras', {})
        assert len(registry.list_versions()) == 1

    def test_prune_keeps_champion(self, tmp_path):
        reg_file = tmp_path / 'registry.json'
        registry = ModelRegistry(registry_path=reg_file)
        registry.register('v1', tmp_path / 'm1.keras', {})
        registry.promote('v1')
        registry.prune(keep=1)
        assert registry.get_champion()['version_id'] == 'v1'

    def test_prune_deletes_old_files(self, tmp_path):
        old_model = tmp_path / 'old.keras'
        old_model.write_bytes(b'x')
        reg_file = tmp_path / 'registry.json'
        registry = ModelRegistry(registry_path=reg_file)
        registry.register('v1', old_model, {})
        registry.register('v2', tmp_path / 'new.keras', {})
        registry.promote('v2')
        registry.prune(keep=1)
        assert not old_model.exists()

    def test_read_corrupted_registry_returns_empty(self, tmp_path):
        reg_file = tmp_path / 'registry.json'
        reg_file.write_text('not json')
        registry = ModelRegistry(registry_path=reg_file)
        assert registry.list_versions() == []
