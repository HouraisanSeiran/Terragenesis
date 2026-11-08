import hashlib
import json
from pathlib import Path
import subprocess
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'tools' / 'prepare_procedural_mountains.py'


def run_cli(*args):
    return subprocess.run([sys.executable, str(SCRIPT), *map(str, args)], cwd=ROOT,
                          capture_output=True, text=True)


def test_invalid_size_refuses_without_output(tmp_path):
    out = tmp_path / 'invalid'
    result = run_cli('--output-dir', out, '--size', '2')
    assert result.returncode != 0
    assert not out.exists()


def test_saved_output_roundtrip_and_no_overwrite(tmp_path):
    out = tmp_path / 'run'
    args = ('--output-dir', out, '--size', '9', '--benchmark-sizes', '4')
    result = run_cli(*args)
    assert result.returncode == 0, result.stderr
    manifest = json.loads((out / 'manifest.json').read_text(encoding='utf-8'))
    record = manifest['rasters'][0]
    path = out / record['file']
    assert hashlib.sha256(path.read_bytes()).hexdigest() == record['sha256']
    with np.load(path, allow_pickle=False) as data:
        assert data['height_m'].shape == (9, 9)
        np.testing.assert_allclose(data['height_m'], data['advanced_base_m'] + data['regional_noise_delta_m'])
        assert data['base_noise_m'].shape == (9, 9)
        metadata = json.loads(str(data['metadata_json']))
        assert metadata['source_family'] == 'independent_procedural_mountains'
        assert metadata['spacing_m'] == 60.0
    assert all(item['nonblank'] for item in manifest['images'].values())
    before = (out / 'manifest.json').read_bytes()
    assert run_cli(*args).returncode != 0
    assert (out / 'manifest.json').read_bytes() == before
