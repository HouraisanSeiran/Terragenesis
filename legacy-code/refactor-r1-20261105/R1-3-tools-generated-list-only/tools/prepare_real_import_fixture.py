"""Export a bounded real Terrain Diffusion height sample for Java import verification."""
from pathlib import Path
import hashlib
import json
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
source = ROOT / 'verification/tuned-model/plains-geographic_v2-seed20260927-x2176-z8832.npz'
target = ROOT / 'verification/real-import/plains-height-f32be.bin'
archive = np.load(source)
metadata = json.loads(archive['metadata'].item())
config = json.loads(archive['generation_config'].item())
assert tuple(metadata['native_origin']) == (2176, 8832)
assert config['blocks_per_pixel'] == 2 and config['meters_per_height_block'] == 6.0
assert archive['elevation'].shape == (513, 513)
height = 62 + archive['elevation'].astype(np.float32) / 6
payload = height.astype('>f4').tobytes(order='C')
target.parent.mkdir(parents=True, exist_ok=True)
if target.exists() and target.read_bytes() != payload:
    raise RuntimeError('Existing bounded fixture differs; inspect before replacing')
if not target.exists():
    target.write_bytes(payload)
report = {
    'source': str(source.relative_to(ROOT)),
    'source_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
    'fixture_sha256': hashlib.sha256(payload).hexdigest(),
    'model_identity': metadata['identity'],
    'seed': int(metadata['seed']),
    'origin_world': [metadata['native_origin'][0] * 2, metadata['native_origin'][1] * 2],
    'shape': [513, 513], 'spacing_blocks': 2,
    'limit': 'real height only; climate and water are not in this fixture',
}
(target.parent / 'provenance.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
print(target)