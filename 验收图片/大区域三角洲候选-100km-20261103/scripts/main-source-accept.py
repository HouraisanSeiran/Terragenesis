"""Independent read-only audit of the regional source, not a generator."""
from pathlib import Path
import hashlib
import json
import numpy as np
from terrain_pipeline.coastal_marine_sediment import load_state

root = Path(__file__).resolve().parent
source = root / 'case-source'
manifest = json.loads((source / 'manifest.json').read_text(encoding='utf-8'))
state = load_state(source / 'state.npz')
with np.load(source / 'source.npz') as data:
    bed = data['source_bed_m']
    base = data['derived_base_bed_m']
    ocean = data['source_ocean']
    unknown = data['unknown_wet']
    valid = data['valid_mask']
    checks = {
        'source_hash': hashlib.sha256((source / 'source.npz').read_bytes()).hexdigest() == manifest['source_sha256'],
        'state_hash': hashlib.sha256((source / 'state.npz').read_bytes()).hexdigest() == manifest['state_sha256'],
        'identity': state.source_identity == manifest['source_identity'],
        'extent_100km': bed.shape == (500, 500) and state.spacing_m == 200. and state.origin_xz_m == (-39900., -39900.),
        'valid_finite': bool(valid.all() and np.isfinite(bed).all() and np.isfinite(base).all()),
        'ocean_base_not_emerged': bool(np.all(base[ocean] < 0)),
        'nonmarine_base_unchanged': bool(np.array_equal(base[~ocean], bed[~ocean])),
        'unknown_not_ocean': bool(not np.any(ocean & unknown)),
        'common_base': bool(np.array_equal(state.base_bed_m, base)),
        'finite_stocks': all(np.isfinite(getattr(state, field)).all() and np.min(getattr(state, field)) >= 0 for field in ('bed_solid_m3', 'mobile_solid_m3', 'stranded_solid_m3')),
    }
    sample_differences = []
    for row, col in ((0, 0), (249, 249), (499, 499), (227, 174), (100, 400), (380, 300)):
        x = state.origin_xz_m[0] + col * state.spacing_m
        z = state.origin_xz_m[1] + row * state.spacing_m
        nx, nz = int(np.floor(x / 30 + .5)), int(np.floor(z / 30 + .5))
        page = next(p for p in manifest['pages'] if p['page_xz'] == [nx // 1024, nz // 1024])
        folder = Path(page['path'])
        pm = json.loads((folder / 'manifest.json').read_text(encoding='utf-8-sig'))
        raw = np.load(folder / 'raw_td.npy', mmap_mode='r')
        ox, oz = pm['origin_native_xz']
        sample_differences.append(float(bed[row, col] - raw[nz-oz, nx-ox]))
    checks['native_td_samples'] = max(map(abs, sample_differences)) == 0

fields = ('bed_solid_m3', 'mobile_solid_m3', 'stranded_solid_m3')
expected = sum(v['inside_m3'] for v in manifest['crop_inventory'].values())
actual = sum(float(getattr(state, field).sum()) for field in fields)
residual = actual - expected
checks['inventory_transfer'] = abs(residual) < 1.
result = {
    'source_identity': state.source_identity, 'checks': checks,
    'inventory_total_m3': actual, 'migration_residual_m3': residual,
    'native_sample_differences_m': sample_differences,
    'pass': bool(all(checks.values())),
}
(root / 'main-source-accept.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
print(json.dumps(result, indent=2))
raise SystemExit(0 if result['pass'] else 1)
