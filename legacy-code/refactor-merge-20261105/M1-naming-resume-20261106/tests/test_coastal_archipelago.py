from pathlib import Path
import numpy as np
import pytest
from terrain_pipeline.coastal_terrain import relief
from terrain_pipeline.coastal_terrain import read_archipelago_product as read_product, prepare_archipelago as prepare
from terrain_pipeline.coastal_terrain import read_terrain_product as read_v1


def fixture():
    bed = np.full((180, 200), -80, np.float32)
    bed[:, :60] = 50
    valid = np.ones(bed.shape, bool)
    support = np.ones(bed.shape, np.float32)
    return bed, valid, support


def test_zero_and_deep_control():
    bed, valid, support = fixture()
    assert np.array_equal(bed + relief(bed, valid, support, (122610, -35430), strength=0), bed)
    support[:] = 0
    assert not relief(bed, valid, support, (122610, -35430)).any()


def test_determinism_shared_support_and_crop_order():
    bed, valid, support = fixture()
    origin = (122610, -35430)
    whole = relief(bed, valid, support, origin)
    def crop(z,x):
        return relief(bed[z:z+100,x:x+100], valid[z:z+100,x:x+100], support[z:z+100,x:x+100], (origin[0]+30*x,origin[1]+30*z))
    assert np.any(whole != 0)
    b, a = crop(50,70), crop(20,20)
    assert np.array_equal(a, whole[20:120,20:120])
    assert np.array_equal(b, whole[50:150,70:170])
    assert np.array_equal(a[30:,50:], b[:70,:50])
    assert np.array_equal(a,crop(20,20))
    assert np.array_equal(b,crop(50,70))


def test_reject_invalid():
    bed, valid, support = fixture()
    with pytest.raises(ValueError): relief(bed, valid, support, (0, 0), strength=float('nan'))
    bed[0, 0] = np.nan
    with pytest.raises(ValueError): relief(bed, valid, support, (0, 0))
    with pytest.raises(ValueError): prepare('missing', 'missing-output', 1, 'bad', 1)



@pytest.fixture
def product_fixture(tmp_path, monkeypatch):
    import json
    from terrain_pipeline import coastal_terrain as product
    from terrain_pipeline.coastal_terrain import classify
    bed, valid, support = fixture()
    origin = (122610, -35430)
    base = {'identity':'source-id', 'origin_xz_m':list(origin), 'spacing_m':30.,
            'terrain_identity':'td', 'raw_file_sha256':'raw', 'macro_identity':'macro',
            'anchor_world_xz_m':[origin[0]+199*30, origin[1]],
            'fixed_source_slice_zx':[0,180,0,200], 'valid_margin_cells':0,
            'anchor_source_zx':[0,199]}
    source = {'bed':bed, 'valid':valid}
    def read_source(path, expected_identity=None):
        if expected_identity != 'source-id':
            raise ValueError('source identity')
        return base, source
    monkeypatch.setattr(product, 'read_terrain_product', read_source)
    r = relief(bed, valid, support, origin, strength=0.7)
    final = bed+r
    codes, shore = classify(final, valid, [product.archipelago_anchor(base)])
    arrays = {'bed':final, 'valid':valid, 'classification':codes, 'shoreline':shore, 'relief':r, 'support':support}
    files = {}
    for name, array in arrays.items():
        np.save(tmp_path/(name+'.npy'), array)
        files[name+'.npy'] = product.file_hash(tmp_path/(name+'.npy'))
    m = {k:base[k] for k in ('origin_xz_m','spacing_m','terrain_identity','raw_file_sha256','macro_identity','anchor_world_xz_m')}
    m.update(schema='coastal-archipelago-v3', algorithm_version='regional-relief-v3',
             baseline_path='fixture', baseline_identity='source-id', shape_zx=list(bed.shape),
             world_seed=20261020, subseed=product.SUBSEED, strength=0.7,
             subseed_derivation='first 8 bytes big endian SHA256 of 20261020:regional-coastal-relief-v3',
             parameters=product.PARAMETERS, noise_helper_sha256=product.file_hash(Path(product.__file__).resolve().parents[1]/'diffusion/geographic_noise.py'), files=files)
    def save():
        m.pop('identity', None)
        m['identity'] = product.identity_archipelago(m)
        (tmp_path/'manifest.json').write_text(json.dumps(m), encoding='utf-8')
    save()
    return tmp_path, m, save


def test_reader_fixture_and_tampering(product_fixture):
    import copy
    path, manifest, save = product_fixture
    read_product(path)
    original = copy.deepcopy(manifest)
    for key, value in [('strength',0.8), ('world_seed',1), ('subseed',1),
                       ('origin_xz_m',[0,0]), ('baseline_identity','other'),
                       ('raw_file_sha256','other')]:
        manifest.clear(); manifest.update(copy.deepcopy(original)); manifest[key] = value; save()
        with pytest.raises(ValueError): read_product(path)
    manifest.clear(); manifest.update(original); save()
    a = np.load(path/'relief.npy'); a[0,0] += 1
    np.save(path/'relief.npy', a)
    from terrain_pipeline.coastal_terrain import file_hash
    manifest['files']['relief.npy'] = file_hash(path/'relief.npy'); save()
    with pytest.raises(ValueError): read_product(path)
