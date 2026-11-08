import json
import sys

import numpy as np
import pytest

from terrain_pipeline import new_world_stage1 as stage
from terrain_pipeline import new_world_stage1_checkpoint as checkpoint


def config(tmp_path):
    return {'schema': 'stage1-checkpoint-v1', 'terrain_path': str(tmp_path / 'terrain'),
            'expected_terrain_identity': 'a' * 64, 'block_size': 5}


def test_checkpoint_rejects_changed_configuration_and_hash(tmp_path):
    root = tmp_path / 'pending'
    root.mkdir()
    cfg = config(tmp_path)
    checkpoint.atomic_json(root / 'checkpoint.json', cfg)
    terrain = tmp_path / 'terrain'
    terrain.mkdir()
    (terrain / 'manifest.json').write_text('{}', encoding='utf-8')
    checkpoint.atomic_json(root / 'source.json', {'phase': 'source', 'config_hash': stage._identity(cfg),
        'source_manifest_sha256': stage._digest(terrain / 'manifest.json')})
    graph = root / 'graph'
    graph.mkdir()
    np.save(graph / 'indices.npy', np.array([1, 2], dtype='i4'))
    checkpoint.atomic_json(root / 'graph.json', {'phase': 'graph', 'config_hash': stage._identity(cfg),
        'files': checkpoint.descriptors(root, 'graph')})
    assert checkpoint.validate(root, cfg) == ['source', 'graph']
    with pytest.raises(ValueError, match='configuration'):
        checkpoint.validate(root, {**cfg, 'block_size': 6})
    np.save(graph / 'indices.npy', np.array([2, 1], dtype='i4'))
    with pytest.raises(ValueError, match='hash'):
        checkpoint.validate(root, cfg)


def test_budget_denial_preserves_pending(tmp_path, monkeypatch):
    monkeypatch.setattr(stage, 'preflight', lambda *args, **kwargs: {'sufficient': True})
    out = tmp_path / 'product'
    with pytest.raises(RuntimeError, match='budget denied'):
        checkpoint.prepare(tmp_path / 'terrain', out, expected_terrain_identity='a' * 64,
                           budget_callback=lambda phase, budget: False)
    assert (tmp_path / 'product.pending' / 'checkpoint.json').exists()
    assert not out.exists()


def test_resource_abort_terminates_own_worker(tmp_path, monkeypatch):
    monkeypatch.setattr(stage, 'preflight', lambda *args, **kwargs: {'sufficient': True})
    monkeypatch.setattr(checkpoint, 'memory', lambda: {'available_ram_bytes': 10 * 1024**3,
                                                        'commit_headroom_bytes': 10 * 1024**3})
    original = checkpoint.subprocess.Popen
    children = []
    def start(*args, **kwargs):
        child = original([sys.executable, '-c', 'import time; time.sleep(30)'])
        children.append(child)
        return child
    monkeypatch.setattr(checkpoint.subprocess, 'Popen', start)
    out = tmp_path / 'product'
    with pytest.raises(RuntimeError, match='resource-abort'):
        checkpoint.prepare(tmp_path / 'terrain', out, expected_terrain_identity='a' * 64,
                           monitor_callback=lambda phase, stats: False)
    assert children[0].poll() is not None
    assert (tmp_path / 'product.pending' / 'checkpoint.json').exists()
    assert not out.exists()
