"""Consolidated tests.test_coastal_terrain implementations; numeric expressions preserved."""
from __future__ import annotations
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as _i9_np
import pytest as _i9_pytest
from terrain_pipeline.coastal_terrain import CoastalParameters as _i9_CoastalParameters
from terrain_pipeline.coastal_terrain import compose as _i9_compose
from terrain_pipeline.coastal_terrain import classify as _i9_classify
from terrain_pipeline.coastal_terrain import coastal_support as _i9_coastal_support
from pathlib import Path as _i10_Path
import numpy as _i10_np
import pytest as _i10_pytest
from terrain_pipeline.coastal_terrain import relief as _i10_relief
from terrain_pipeline.coastal_terrain import read_archipelago_product as _i10_read_product
from terrain_pipeline.coastal_terrain import prepare_archipelago as _i10_prepare
from terrain_pipeline.coastal_terrain import read_terrain_product as _i10_read_v1
import json as _i11_json
from pathlib import Path as _i11_Path
import numpy as _i11_np
import pytest as _i11_pytest
from terrain_pipeline.coastal_terrain import classify as _i11_classify
from terrain_pipeline import coastal_terrain as _i11_product
from dataclasses import replace as _i12_replace
import numpy as _i12_np
import pytest as _i12_pytest
from terrain_pipeline.coastal_terrain import classify as _i12_classify
from terrain_pipeline.coastal_terrain import DetailParameters as _i12_DetailParameters
from terrain_pipeline.coastal_terrain import detail_support as _i12_detail_support
from terrain_pipeline.coastal_terrain import refine as _i12_refine

CATEGORY = 'B'

# Source: tests.test_coastal_terrain
def support_for(macro, params):
    wet = _i9_np.argwhere(macro < params.sea_m)
    anchors = [tuple(wet[0])] if wet.size else None
    return _i9_coastal_support(macro, params, anchors=anchors)

# Source: tests.test_coastal_terrain
P = _i9_CoastalParameters(spacing_m=1, sigma_m=1, radius_m=2, transition_elevation_m=10, nearshore_allowance_m=5, coast_band_m=10)

# Source: tests.test_coastal_terrain
def test_zero_and_fixed_support_overlap():
    rng = _i9_np.random.default_rng(14)
    macro = rng.normal(size=(30, 32)).astype('f4')
    assert _i9_np.array_equal(_i9_compose(macro, macro, P, support=support_for(macro, P)), macro[2:-2, 2:-2])
    raw = macro + rng.normal(size=macro.shape).astype('f4')
    before = raw.copy()
    full = _i9_compose(raw, macro, P, support=support_for(macro, P))
    support = support_for(macro, P)
    full = _i9_compose(raw, macro, P, support=support)
    partial = _i9_compose(raw[5:25, 7:27], macro[5:25, 7:27], P, support=support[5:25, 7:27])
    _i9_np.testing.assert_array_equal(full[5:21, 7:23], partial)
    _i9_np.testing.assert_array_equal(raw, before)
    raw[1, 1] = _i9_np.nan
    with _i9_pytest.raises(ValueError):
        _i9_compose(raw, macro, P, support=support_for(macro, P))
    with _i9_pytest.raises(ValueError):
        _i9_compose(raw[:4, :4], macro[:4, :4], P, support=_i9_np.zeros((4, 4)))

# Source: tests.test_coastal_terrain
def test_nearshore_changes_sign_far_stays_locked():
    macro = _i9_np.full((12, 40), -1.0)
    macro[:, 20:] = 1.0
    raw = macro + _i9_np.where(macro < 0, 50.0, -50.0)
    bed = _i9_compose(raw, macro, P, support=support_for(macro, P))
    assert bed[4, 15] > 0 and bed[4, 20] < 0
    macro = _i9_np.full((9, 9), 100.0)
    assert (_i9_compose(macro - 1000, macro, P, support=support_for(macro, P)) > 0).all()

# Source: tests.test_coastal_terrain
def test_classification_unknown_enclosed_and_updated_shore():
    bed = _i9_np.ones((7, 7))
    bed[:, 0] = -1
    bed[3, 3] = -1
    bed[0, 6] = -1
    codes, shore = _i9_classify(bed, _i9_np.ones_like(bed, dtype=bool), [(2, 0)])
    assert codes[3, 3] == 3 and codes[0, 6] == 0 and (codes[2, 0] == 2)
    assert shore[2, 1]
    bed[2, 1] = -1
    newer, shore2 = _i9_classify(bed, _i9_np.ones_like(bed, dtype=bool), [(2, 0)])
    assert newer[2, 1] == 2 and (not shore2[2, 1]) and shore2[2, 2]
    with _i9_pytest.raises(ValueError):
        _i9_classify(bed, _i9_np.ones_like(bed, dtype=bool), [(3, 2)])

# Source: tests.test_coastal_terrain
def test_no_coast_and_fixed_support():
    assert not _i9_coastal_support(_i9_np.ones((20, 20)), P).any()
    assert not _i9_coastal_support(-_i9_np.ones((20, 20)), P).any()
    macro = _i9_np.ones((30, 50))
    macro[:, :5] = -1
    support = support_for(macro, P)
    assert not support[:, 25:].any()
    assert not _i9_coastal_support(macro[:, 25:], P).any()

# Source: tests.test_coastal_terrain
def test_support_monotone_and_explicit():
    macro = _i9_np.ones((30, 50))
    macro[:, :10] = -1
    support = support_for(macro, P)
    assert _i9_np.all(_i9_np.diff(support[15, 10:]) <= 0)
    with _i9_pytest.raises(ValueError):
        _i9_compose(macro, macro, P)

# Source: tests.test_coastal_terrain
def test_preflight_before_load_and_no_output(tmp_path, monkeypatch):
    from terrain_pipeline.coastal_terrain import prepare_terrain_bed as prepare

    def forbidden(*args, **kwargs):
        raise AssertionError('array loading before preflight')
    monkeypatch.setattr(_i9_np, 'load', forbidden)
    output = tmp_path / 'missing' / 'product'
    with _i9_pytest.raises(ValueError, match='budget'):
        prepare('raw', 'macro', 'metadata', output, memory_budget_bytes=1)
    assert not output.exists()

# Source: tests.test_coastal_terrain
def test_reader_detects_tampering(tmp_path):
    import hashlib, json
    from terrain_pipeline.coastal_terrain import read_terrain_product as read_product
    from terrain_pipeline.coastal_terrain import file_hash
    bed = _i9_np.ones((5, 5), _i9_np.float32)
    bed[:, 0] = -1
    codes, shore = _i9_classify(bed, _i9_np.ones((5, 5), bool), [(2, 0)])
    files = {}
    for name, arr in (('bed', bed), ('classification', codes), ('shoreline', shore), ('valid', _i9_np.ones((5, 5), bool))):
        path = tmp_path / (name + '.npy')
        _i9_np.save(path, arr)
        files[path.name] = file_hash(path)
    manifest = {'schema': 'coastal-terrain-v1', 'files': files, 'shape_zx': [5, 5], 'fixed_source_slice_zx': [1914, 1921, 2983, 2990], 'valid_margin_cells': 1, 'source_shape_zx': [3834, 3834], 'source_origin_xz_m': [100530, -57510], 'origin_xz_m': [190050, -60], 'spacing_m': 30, 'algorithm_version': 'coastal-bed-v1', 'anchor_source_zx': [1917, 2984], 'anchor_world_xz_m': [190050, 0], 'parameters': {'spacing_m': 30, 'sigma_m': 30, 'radius_m': 30, 'transition_elevation_m': 300, 'coast_band_m': 30, 'nearshore_allowance_m': 200, 'far_fraction': 0.85, 'low_fraction': 0.65, 'sea_m': 0}}
    manifest['identity'] = hashlib.sha256(json.dumps(manifest, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    path = tmp_path / 'manifest.json'
    path.write_text(json.dumps(manifest))
    _, arrays = read_product(tmp_path, expected_identity=manifest['identity'])
    assert not arrays['bed'].flags.writeable
    manifest['shape_zx'] = [5, 4]
    path.write_text(json.dumps(manifest))
    with _i9_pytest.raises(ValueError, match='identity'):
        read_product(tmp_path)
    manifest['shape_zx'] = [5, 5]
    manifest['origin_xz_m'][0] += 30
    manifest.pop('identity')
    manifest['identity'] = hashlib.sha256(json.dumps(manifest, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    path.write_text(json.dumps(manifest))
    with _i9_pytest.raises(ValueError, match='coordinates'):
        read_product(tmp_path)
    manifest['origin_xz_m'][0] -= 30
    codes[2, 2] = 2
    _i9_np.save(tmp_path / 'classification.npy', codes)
    manifest['files']['classification.npy'] = file_hash(tmp_path / 'classification.npy')
    manifest.pop('identity')
    manifest['identity'] = hashlib.sha256(json.dumps(manifest, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    path.write_text(json.dumps(manifest))
    with _i9_pytest.raises(ValueError, match='classification'):
        read_product(tmp_path)

# Source: tests.test_coastal_terrain
def test_enclosed_macro_depression_is_not_coast():
    macro = _i9_np.ones((60, 80))
    macro[:, :5] = -1
    macro[30, 50] = -1
    support = _i9_coastal_support(macro, P, anchors=[(20, 0)])
    assert support[30, 50] == 0
    assert support[30, 5] > 0

# Source: tests.test_coastal_terrain
def test_curved_coast_shared_support_overlapping_tiles():
    z, x = _i9_np.indices((90, 100))
    macro = (x - (45 + 8 * _i9_np.sin(z / 12))).astype(_i9_np.float32)
    raw = macro + 7 * _i9_np.sin(x / 4) * _i9_np.cos(z / 7)
    support = _i9_coastal_support(macro, P, anchors=[(40, 0)])
    full = _i9_compose(raw, macro, P, support=support)
    for window, target in ((_i9_np.s_[10:70, 5:75], _i9_np.s_[10:66, 5:71]), (_i9_np.s_[25:85, 20:90], _i9_np.s_[25:81, 20:86])):
        _i9_np.testing.assert_array_equal(_i9_compose(raw[window], macro[window], P, support=support[window]), full[target])

# Source: tests.test_coastal_terrain
def test_staging_failure_does_not_publish(tmp_path, monkeypatch):
    import json
    from types import SimpleNamespace
    from terrain_pipeline import coastal_terrain as product
    metadata = tmp_path / 'metadata.json'
    metadata.write_text(json.dumps({'terrain_identity': product.TD_ID, 'source_shape_zx': [3834, 3834], 'source_origin_native_xz': [3351, -1917], 'native_spacing_m': 30}))
    monkeypatch.setattr(product.psutil, 'virtual_memory', lambda: SimpleNamespace(available=2000000000))
    monkeypatch.setattr(product, 'file_hash', lambda path: product.RAW_HASH if str(path) == 'raw' else product.MACRO_HASH)
    monkeypatch.setattr(product, 'array_hash_contiguous', lambda a: product.RAW_ARRAY if a[0, 0] == 1 else product.MACRO_ARRAY)
    monkeypatch.setattr(product.np, 'load', lambda path, **kw: _i9_np.broadcast_to(_i9_np.float32(1 if str(path) == 'raw' else 2), (3834, 3834)))
    monkeypatch.setattr(product, 'coastal_support', lambda macro, params, **kw: _i9_np.zeros(macro.shape, _i9_np.float32))
    monkeypatch.setattr(product, 'compose', lambda raw, macro, params, **kw: _i9_np.zeros((raw.shape[0] - 192, raw.shape[1] - 192), _i9_np.float32))
    monkeypatch.setattr(product, 'classify', lambda bed, valid, anchors: (_i9_np.zeros(bed.shape, _i9_np.uint8), _i9_np.zeros(bed.shape, bool)))

    def fail(*args, **kwargs):
        raise OSError('simulated write failure')
    monkeypatch.setattr(product.np, 'save', fail)
    output = tmp_path / 'product'
    with _i9_pytest.raises(OSError, match='simulated'):
        product.prepare_terrain_bed('raw', 'macro', metadata, output)
    assert not output.exists() and (not list(tmp_path.glob('.coast-*')))

# Source: tests.test_coastal_archipelago
def fixture():
    bed = _i10_np.full((180, 200), -80, _i10_np.float32)
    bed[:, :60] = 50
    valid = _i10_np.ones(bed.shape, bool)
    support = _i10_np.ones(bed.shape, _i10_np.float32)
    return (bed, valid, support)

# Source: tests.test_coastal_archipelago
def test_zero_and_deep_control():
    bed, valid, support = fixture()
    assert _i10_np.array_equal(bed + _i10_relief(bed, valid, support, (122610, -35430), strength=0), bed)
    support[:] = 0
    assert not _i10_relief(bed, valid, support, (122610, -35430)).any()

# Source: tests.test_coastal_archipelago
def test_determinism_shared_support_and_crop_order():
    bed, valid, support = fixture()
    origin = (122610, -35430)
    whole = _i10_relief(bed, valid, support, origin)

    def crop(z, x):
        return _i10_relief(bed[z:z + 100, x:x + 100], valid[z:z + 100, x:x + 100], support[z:z + 100, x:x + 100], (origin[0] + 30 * x, origin[1] + 30 * z))
    assert _i10_np.any(whole != 0)
    b, a = (crop(50, 70), crop(20, 20))
    assert _i10_np.array_equal(a, whole[20:120, 20:120])
    assert _i10_np.array_equal(b, whole[50:150, 70:170])
    assert _i10_np.array_equal(a[30:, 50:], b[:70, :50])
    assert _i10_np.array_equal(a, crop(20, 20))
    assert _i10_np.array_equal(b, crop(50, 70))

# Source: tests.test_coastal_archipelago
def test_reject_invalid():
    bed, valid, support = fixture()
    with _i10_pytest.raises(ValueError):
        _i10_relief(bed, valid, support, (0, 0), strength=float('nan'))
    bed[0, 0] = _i10_np.nan
    with _i10_pytest.raises(ValueError):
        _i10_relief(bed, valid, support, (0, 0))
    with _i10_pytest.raises(ValueError):
        _i10_prepare('missing', 'missing-output', 1, 'bad', 1)

# Source: tests.test_coastal_archipelago
@_i10_pytest.fixture
def product_fixture(tmp_path, monkeypatch):
    import json
    from terrain_pipeline import coastal_terrain as product
    from terrain_pipeline.coastal_terrain import classify
    bed, valid, support = fixture()
    origin = (122610, -35430)
    base = {'identity': 'source-id', 'origin_xz_m': list(origin), 'spacing_m': 30.0, 'terrain_identity': 'td', 'raw_file_sha256': 'raw', 'macro_identity': 'macro', 'anchor_world_xz_m': [origin[0] + 199 * 30, origin[1]], 'fixed_source_slice_zx': [0, 180, 0, 200], 'valid_margin_cells': 0, 'anchor_source_zx': [0, 199]}
    source = {'bed': bed, 'valid': valid}

    def read_source(path, expected_identity=None):
        if expected_identity != 'source-id':
            raise ValueError('source identity')
        return (base, source)
    monkeypatch.setattr(product, 'read_terrain_product', read_source)
    r = _i10_relief(bed, valid, support, origin, strength=0.7)
    final = bed + r
    codes, shore = classify(final, valid, [product.archipelago_anchor(base)])
    arrays = {'bed': final, 'valid': valid, 'classification': codes, 'shoreline': shore, 'relief': r, 'support': support}
    files = {}
    for name, array in arrays.items():
        _i10_np.save(tmp_path / (name + '.npy'), array)
        files[name + '.npy'] = product.file_hash(tmp_path / (name + '.npy'))
    m = {k: base[k] for k in ('origin_xz_m', 'spacing_m', 'terrain_identity', 'raw_file_sha256', 'macro_identity', 'anchor_world_xz_m')}
    m.update(schema='coastal-archipelago-v3', algorithm_version='regional-relief-v3', baseline_path='fixture', baseline_identity='source-id', shape_zx=list(bed.shape), world_seed=20261020, subseed=product.SUBSEED, strength=0.7, subseed_derivation='first 8 bytes big endian SHA256 of 20261020:regional-coastal-relief-v3', parameters=product.PARAMETERS, noise_helper_sha256=product.file_hash(_i10_Path(product.__file__).resolve().parents[1] / 'diffusion/geographic_noise.py'), files=files)

    def save():
        m.pop('identity', None)
        m['identity'] = product.identity_archipelago(m)
        (tmp_path / 'manifest.json').write_text(json.dumps(m), encoding='utf-8')
    save()
    return (tmp_path, m, save)

# Source: tests.test_coastal_archipelago
def test_reader_fixture_and_tampering(product_fixture):
    import copy
    path, manifest, save = product_fixture
    _i10_read_product(path)
    original = copy.deepcopy(manifest)
    for key, value in [('strength', 0.8), ('world_seed', 1), ('subseed', 1), ('origin_xz_m', [0, 0]), ('baseline_identity', 'other'), ('raw_file_sha256', 'other')]:
        manifest.clear()
        manifest.update(copy.deepcopy(original))
        manifest[key] = value
        save()
        with _i10_pytest.raises(ValueError):
            _i10_read_product(path)
    manifest.clear()
    manifest.update(original)
    save()
    a = _i10_np.load(path / 'relief.npy')
    a[0, 0] += 1
    _i10_np.save(path / 'relief.npy', a)
    from terrain_pipeline.coastal_terrain import file_hash
    manifest['files']['relief.npy'] = file_hash(path / 'relief.npy')
    save()
    with _i10_pytest.raises(ValueError):
        _i10_read_product(path)

# Source: tests.test_coastal_detail_product
@_i11_pytest.fixture
def source(tmp_path):
    root = tmp_path / 'source'
    root.mkdir()
    z, x = _i11_np.indices((90, 110))
    raw = ((x - 55) * 0.4 + 15 * _i11_np.sin(x / 3) * _i11_np.cos(z / 4)).astype(_i11_np.float32)
    raw_path = root / 'raw.npy'
    _i11_np.save(raw_path, raw)
    bed = _i11_np.broadcast_to(((_i11_np.arange(100) - 50) * 0.4).astype(_i11_np.float32), (80, 100)).copy()
    valid = _i11_np.ones(bed.shape, bool)
    codes, shore = _i11_classify(bed, valid, [(40, 0)])
    files = {}
    for name, a in (('bed', bed), ('valid', valid), ('classification', codes), ('shoreline', shore)):
        path = root / (name + '.npy')
        _i11_np.save(path, a)
        files[path.name] = _i11_product.file_hash(path)
    metadata = {'terrain_identity': 'portable-td-fixture', 'world_seed': 20261020, 'source_shape_zx': [90, 110], 'native_spacing_m': 30, 'native_source_origin_xz_m': [3000, -6000], 'source_origin_native_xz': [100, -200], 'native_source_paths': {'raw_td_30m': {'path': str(raw_path), 'sha256': _i11_product.file_hash(raw_path), 'array_sha256': _i11_product.array_hash_rowchunk(raw)}}}
    metadata_path = root / 'metadata.json'
    metadata_path.write_text(_i11_json.dumps(metadata), encoding='utf-8')
    record = {'kind': 'frozen-detail-source-v1', 'baseline_path': str(root), 'baseline_identity': '', 'files': files, 'raw_path': str(raw_path), 'raw_file_sha256': _i11_product.file_hash(raw_path), 'raw_array_sha256': _i11_product.array_hash_rowchunk(raw), 'metadata_path': str(metadata_path), 'metadata_sha256': _i11_product.file_hash(metadata_path), 'terrain_identity': 'portable-td-fixture', 'world_seed': 20261020, 'shape_zx': [80, 100], 'origin_xz_m': [3150, -5850], 'spacing_m': 30, 'source_shape_zx': [90, 110], 'source_origin_xz_m': [3000, -6000], 'source_slice_zx': [5, 85, 5, 105], 'anchors_zx': [[40, 0]]}
    record['baseline_identity'] = _i11_product._frozen_baseline_identity(record)
    return record

# Source: tests.test_coastal_detail_product
def reseal(path, manifest):
    manifest['identity'] = _i11_product.identity_detail(manifest)
    (path / 'manifest.json').write_text(_i11_json.dumps(manifest), encoding='utf-8')

# Source: tests.test_coastal_detail_product
def test_portable_roundtrip_readonly_no_overwrite(source, tmp_path):
    output = tmp_path / 'product'
    manifest = _i11_product.prepare_source(source, output)
    _, arrays = _i11_product.read_detail_product(output, expected_identity=manifest['identity'])
    assert _i11_np.any(arrays['delta'])
    for a in arrays.values():
        assert not a.flags.writeable
        with _i11_pytest.raises(ValueError):
            a.flat[0] = 0
    with _i11_pytest.raises(FileExistsError):
        _i11_product.prepare_source(source, output)
    copy = _i11_json.loads(_i11_json.dumps(manifest))
    copy['source']['raw_path'] = 'another-machine/raw.npy'
    copy['source']['baseline_path'] = 'another-machine/baseline'
    assert _i11_product.identity_detail(copy) == manifest['identity']

# Source: tests.test_coastal_detail_product
@_i11_pytest.mark.parametrize('field', ['bed', 'delta', 'valid', 'classification', 'shoreline', 'weight', 'distance_m'])
def test_resealed_array_forgery_rejected(source, tmp_path, field):
    output = tmp_path / 'product'
    m = _i11_product.prepare_source(source, output)
    path = output / (field + '.npy')
    a = _i11_np.load(path)
    if a.dtype == _i11_np.bool_:
        a[40, 50] = ~a[40, 50]
    else:
        a[40, 50] += 1
    _i11_np.save(path, a)
    m['files'][path.name] = _i11_product.file_hash(path)
    reseal(output, m)
    with _i11_pytest.raises(ValueError, match='derived relation'):
        _i11_product.read_detail_product(output)

# Source: tests.test_coastal_detail_product
@_i11_pytest.mark.parametrize('change', ['raw', 'metadata', 'mapping', 'parameters', 'seed', 'algorithm', 'source-hash'])
def test_source_and_manifest_failures(source, tmp_path, change):
    output = tmp_path / 'product'
    m = _i11_product.prepare_source(source, output)
    if change in {'raw', 'metadata'}:
        path = _i11_Path(source[change + '_path'])
        with path.open('ab') as stream:
            stream.write(b'tamper')
    elif change == 'mapping':
        m['source']['source_slice_zx'] = [4, 84, 5, 105]
    elif change == 'parameters':
        m['parameters']['cap_m'] = 7
    elif change == 'seed':
        m['source']['world_seed'] = 0
    elif change == 'algorithm':
        m['algorithm_sha256']['coastal_detail_refinement.py'] = '0' * 64
    else:
        m['source']['raw_array_sha256'] = '0' * 64
    reseal(output, m)
    with _i11_pytest.raises(ValueError):
        _i11_product.read_detail_product(output)

# Source: tests.test_coastal_detail_product
def test_mapping_checked_even_with_rehashed_metadata(source, tmp_path):
    metadata_path = _i11_Path(source['metadata_path'])
    metadata = _i11_json.loads(metadata_path.read_text())
    metadata['native_source_origin_xz_m'][0] += 30
    metadata_path.write_text(_i11_json.dumps(metadata))
    source['metadata_sha256'] = _i11_product.file_hash(metadata_path)
    with _i11_pytest.raises(ValueError, match='coordinates'):
        _i11_product.prepare_source(source, tmp_path / 'output')

# Source: tests.test_coastal_detail_product
def test_preflight_and_staging_failure(source, tmp_path, monkeypatch):
    output = tmp_path / 'product'
    with _i11_pytest.raises(ValueError, match='budget'):
        _i11_product.prepare_source(source, output, memory_budget_bytes=1)

    def fail(*args, **kwargs):
        raise OSError('simulated write failure')
    monkeypatch.setattr(_i11_product.np, 'save', fail)
    with _i11_pytest.raises(OSError, match='simulated'):
        _i11_product.prepare_source(source, output)
    assert not output.exists()
    assert not list(tmp_path.glob('.coastal-detail-*'))

# Source: tests.test_coastal_detail_product
def test_real_entry_rejects_unapproved_baseline(source, tmp_path):
    path = _i11_Path(source['baseline_path'])
    (path / 'manifest.json').write_text(_i11_json.dumps({'identity': 'unapproved'}))
    with _i11_pytest.raises(ValueError, match='approved baseline'):
        _i11_product.prepare_detail(path, tmp_path / 'product')

# Source: tests.test_coastal_detail_product
def test_relocated_source_bytes_preserve_identity(source, tmp_path):
    import shutil
    output = tmp_path / 'product'
    m = _i11_product.prepare_source(source, output)
    relocated = tmp_path / 'relocated'
    shutil.copytree(source['baseline_path'], relocated)
    for key in ('baseline_path', 'raw_path', 'metadata_path'):
        original = _i11_Path(m['source'][key])
        m['source'][key] = str(relocated if key == 'baseline_path' else relocated / original.name)
    assert _i11_product.identity_detail(m) == m['identity']
    reseal(output, m)
    _i11_product.read_detail_product(output, expected_identity=m['identity'])

# Source: tests.test_coastal_detail_product
def test_incomplete_parameters_rejected(source, tmp_path):
    output = tmp_path / 'product'
    m = _i11_product.prepare_source(source, output)
    del m['parameters']['strength']
    reseal(output, m)
    with _i11_pytest.raises(ValueError, match='incomplete'):
        _i11_product.read_detail_product(output)

# Source: tests.test_coastal_detail_refinement
def terrain():
    z, x = _i12_np.indices((120, 160))
    bed = ((x - 78) * 0.45 + 0.7 * _i12_np.sin(z / 9)).astype(_i12_np.float32)
    raw = (bed + 24 * _i12_np.sin(x / 2.7) * _i12_np.cos(z / 3.5)).astype(_i12_np.float32)
    valid = _i12_np.ones(bed.shape, bool)
    codes, shore = _i12_classify(bed, valid, [(60, 0)])
    return (raw, bed, valid, codes, shore)

# Source: tests.test_coastal_detail_refinement
def test_bounded_support_and_sign_changes_deterministic():
    raw, bed, valid, codes, shore = terrain()
    support = _i12_detail_support(bed, valid, codes, shore)
    before = (bed.copy(), raw.copy())
    result, delta = _i12_refine(raw, bed, support=support)
    assert _i12_np.any(delta != 0)
    assert _i12_np.max(_i12_np.abs(delta)) <= 6.00001
    protected = (support['distance_m'] >= 240) | (_i12_np.abs(bed) >= 40) | ~valid
    _i12_np.testing.assert_array_equal(result[protected], bed[protected])
    changed_sign = (result < 0) != (bed < 0)
    assert changed_sign.any()
    assert _i12_np.max(support['distance_m'][changed_sign]) < 90
    _i12_np.testing.assert_array_equal(_i12_refine(raw, bed, support=support)[0], result)
    _i12_np.testing.assert_array_equal(result - bed, delta)
    _i12_np.testing.assert_array_equal(bed, before[0])
    _i12_np.testing.assert_array_equal(raw, before[1])

# Source: tests.test_coastal_detail_refinement
def test_shared_support_offset_halos_are_bitwise_identical():
    raw, bed, valid, codes, shore = terrain()
    support = _i12_detail_support(bed, valid, codes, shore)
    full, _ = _i12_refine(raw, bed, support=support)
    for z0, z1, x0, x1 in [(3, 105, 21, 137), (12, 118, 38, 150)]:
        window = _i12_np.s_[z0:z1, x0:x1]
        cropped, _ = _i12_refine(raw[window], bed[window], support={k: a[window] for k, a in support.items()})
        _i12_np.testing.assert_array_equal(cropped[24:-24, 24:-24], full[z0 + 24:z1 - 24, x0 + 24:x1 - 24])

# Source: tests.test_coastal_detail_refinement
def test_zero_equal_and_flat_inputs_do_not_invent_detail():
    raw, bed, valid, codes, shore = terrain()
    support = _i12_detail_support(bed, valid, codes, shore)
    _i12_np.testing.assert_array_equal(_i12_refine(raw, bed, support=support, params=_i12_replace(_i12_DetailParameters(), strength=0))[0], bed)
    _i12_np.testing.assert_array_equal(_i12_refine(bed, bed, support=support)[0], bed)
    flat = _i12_np.full_like(bed, 2)
    fake_support = {'weight': _i12_np.ones_like(bed), 'distance_m': _i12_np.zeros_like(bed)}
    _i12_np.testing.assert_array_equal(_i12_refine(flat + 10, flat, support=fake_support)[0], flat)
    no_coast = _i12_detail_support(flat, valid, _i12_np.ones_like(codes), _i12_np.zeros_like(shore))
    assert not no_coast['weight'].any()

# Source: tests.test_coastal_detail_refinement
def test_unknown_enclosed_and_invalid_are_protected():
    raw, bed, valid, _, _ = terrain()
    bed[:, 80:83] = 1
    bed[0:15, 83:85] = -1
    bed[60, 84] = -1
    valid[45:50, 84] = False
    codes, shore = _i12_classify(bed, valid, [(60, 0)])
    support = _i12_detail_support(bed, valid, codes, shore)
    result, _ = _i12_refine(raw, bed, support=support)
    protected = ~valid | (bed < 0) & (codes != 2)
    _i12_np.testing.assert_array_equal(result[protected], bed[protected])
    final_codes, _ = _i12_classify(result, valid, [(60, 0)])
    _i12_np.testing.assert_array_equal(final_codes[protected], codes[protected])

# Source: tests.test_coastal_detail_refinement
@_i12_pytest.mark.parametrize('changes', [{'strength': -1}, {'strength': float('nan')}, {'cap_m': 6.1}, {'radius_m': 750}, {'coast_band_m': 241}, {'elevation_band_m': 41}, {'sign_band_m': 91}, {'sigma_short_m': 190}, {'spacing_m': 31}])
def test_parameter_rejection(changes):
    with _i12_pytest.raises(ValueError):
        _i12_replace(_i12_DetailParameters(), **changes).validate()

# Source: tests.test_coastal_detail_refinement
def test_bad_arrays_and_support_rejected():
    raw, bed, valid, codes, shore = terrain()
    support = _i12_detail_support(bed, valid, codes, shore)
    with _i12_pytest.raises(ValueError):
        _i12_refine(raw[:40, :40], bed[:40, :40], support={k: a[:40, :40] for k, a in support.items()})
    raw[60, 75] = _i12_np.nan
    with _i12_pytest.raises(ValueError):
        _i12_refine(raw, bed, support=support)
    with _i12_pytest.raises(ValueError):
        _i12_refine(bed, bed, support={'weight': support['weight']})
