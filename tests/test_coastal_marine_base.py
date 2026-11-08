import numpy as np
from pathlib import Path
from terrain_pipeline.coastal_marine_base import reorganize
from terrain_pipeline.coastal_marine_product import load_product, prepare

SOURCE = Path('.scratch/delta-scale-suite-20261102/source-case300')


def test_real_source_preservation_and_determinism(tmp_path):
    manifest, a = prepare(SOURCE, tmp_path / 'product')
    _, loaded = load_product(tmp_path / 'product')
    for key in a:
        np.testing.assert_array_equal(a[key], loaded[key])
    ocean = a['source_ocean']
    np.testing.assert_array_equal(a['source_bed'][~ocean], a['derived_base_bed'][~ocean])
    assert np.all(a['derived_base_bed'][ocean] < 0)
    assert np.ptp(a['shelf_width_m'][ocean]) > 5000
    assert np.std(a['derived_base_bed'][ocean & (a['coast_distance_m'] < 20000)]) > 20
    np.testing.assert_array_equal(a['base_change_m'][0], 0)
    again = reorganize(a['source_bed'], a['valid'], ocean, np.load(SOURCE / 'unknown_wet.npy'), manifest['spacing_m'], continental_fraction=a['continental_fraction'], crust_thickness_m=a['crust_thickness_m'])
    np.testing.assert_allclose(a['derived_base_bed'], again['derived_base_bed'], atol=0.0003, rtol=0)
    _, repeat = prepare(SOURCE, tmp_path / 'repeat')
    np.testing.assert_array_equal(a['derived_base_bed'], repeat['derived_base_bed'])
    crop = np.s_[70:260, 100:350]
    np.testing.assert_array_equal(loaded['derived_base_bed'][crop], repeat['derived_base_bed'][crop])
    assert manifest['source_identity'] == '4fc3ec6ac77d2ea49dafa2242b5012871ee8c61b8d5b23f155d48ca3acff1a01'


def test_unknown_and_enclosed_negative_preserved():
    bed = np.full((50, 80), -1000, np.float32)
    bed[:, :25] = 100
    bed[20, 10] = -10
    bed[25, 11] = -20
    valid = np.ones_like(bed, bool)
    ocean = np.zeros_like(valid); ocean[:, 25:] = True
    unknown = np.zeros_like(valid); unknown[20, 10] = True
    a = reorganize(bed, valid, ocean, unknown, 600)
    assert a['classification'][20, 10] == 0
    assert a['classification'][25, 11] == 3
    assert a['derived_base_bed'][20, 10] == -10
    assert a['derived_base_bed'][25, 11] == -20


def test_tectonic_fields_are_sampled_and_control_width(tmp_path):
    from terrain_pipeline.tectonic import load_product as load_plate
    manifest, a = prepare(SOURCE, tmp_path / 'base')
    plate = load_plate(manifest['plate_path'], expected_identity=manifest['plate_identity'])
    z, x = 200, 250
    sampled = plate.sample(manifest['origin_xz_m'][0] + x * manifest['spacing_m'],
                           manifest['origin_xz_m'][1] + z * manifest['spacing_m'], outside='reject')
    np.testing.assert_allclose(a['continental_fraction'][z, x], sampled['continental_fraction'], rtol=1e-6)
    np.testing.assert_allclose(a['crust_thickness_m'][z, x], sampled['crust_thickness_m'], rtol=1e-6)
    alternate = reorganize(a['source_bed'], a['valid'], a['source_ocean'], np.load(SOURCE / 'unknown_wet.npy'),
                           manifest['spacing_m'], continental_fraction=np.zeros_like(a['source_bed']),
                           crust_thickness_m=np.full_like(a['source_bed'], 7000))
    assert np.max(np.abs(a['shelf_width_m'] - alternate['shelf_width_m'])) > 5000
    assert np.ptp(a['shelf_slope'][a['source_ocean']]) > 0.001


def test_invalid_cells_do_not_poison_marine_context():
    bed = np.full((70, 90), -500, np.float32)
    bed[:, :20] = 100
    valid = np.ones_like(bed, bool); valid[25:30, 40:45] = False
    bed[~valid] = np.nan
    ocean = valid & (bed < 0)
    a = reorganize(bed, valid, ocean, np.zeros_like(valid), 600)
    assert np.isfinite(a['derived_base_bed'][valid]).all()
    assert np.isnan(a['derived_base_bed'][~valid]).all()
    np.testing.assert_array_equal(a['source_bed'][valid & ~ocean], a['derived_base_bed'][valid & ~ocean])
