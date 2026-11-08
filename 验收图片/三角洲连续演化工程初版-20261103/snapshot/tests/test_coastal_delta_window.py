import numpy as np
from terrain_pipeline.coastal_delta_window import classify, geological_base, migrate_volume, sample_pages


def test_overlap_noninteger_crop_conserves():
    old = np.array([[12., 24.], [36., 48.]])
    new = migrate_volume(old, (0., 0.), 3., (4, 4), (-.75, -.75), 1.5)
    assert np.isclose(new.sum(), old.sum())
    cropped = migrate_volume(old, (0., 0.), 3., (1, 1), (0., 0.), 2.)
    assert np.isclose(cropped.sum(), 12 * 4 / 9)


def test_ocean_requires_boundary_parent_and_connectivity():
    bed = np.ones((5, 5)); bed[0:2, 0] = -1; bed[3, 3] = -1; bed[0, 4] = -1
    valid = np.ones((5, 5), bool); valid[1, 0] = False
    parent = np.zeros((5, 5), bool); parent[0, 0] = True
    ocean, unknown, seeds = classify(bed, valid, parent)
    assert ocean.sum() == 1 and seeds.sum() == 1 and unknown.sum() == 2
    assert not ocean[1, 0] and not ocean[3, 3]


def test_missing_page_stays_unknown():
    bed, pages = sample_pages({'pages': []}, shape=(2, 2), origin=(0, 0), spacing=100)
    assert np.isnan(bed).all() and pages == []


def test_depth_limited_uplift_preserves_relief_land_and_negative_change():
    bed = np.array([[-0.1, -0.3, -1., -3., -7., 4., -2.]])
    ocean = np.array([[True, True, True, True, True, False, False]])
    change = np.array([[100., 100., 100., 100., -2., 100., 100.]])
    result = geological_base(bed, np.ones_like(ocean), ocean, change)
    assert np.all(result[ocean] < 0)
    assert len(np.unique(result[0, :4])) == 4
    assert np.allclose(result[0, :4], bed[0, :4] * .1, atol=1e-12)
    assert result[0, 4] == -9. and result[0, 5] == 4. and result[0, 6] == -2.
    small = geological_base(np.array([[-100.]]), np.ones((1, 1), bool), np.ones((1, 1), bool), np.array([[.001]]))
    assert np.isclose(small[0, 0], -99.999, atol=1e-7)


def test_produced_window_cold_read_and_inventory():
    import json
    from pathlib import Path
    from terrain_pipeline.coastal_marine_product import file_hash
    from terrain_pipeline.coastal_marine_sediment import load_state
    path = Path('.scratch/coast-marine-reorganization-20261102/window100-v2')
    if not path.exists():
        import pytest
        pytest.skip('real source artifact not built')
    manifest = json.loads((path / 'manifest.json').read_text(encoding='utf-8-sig'))
    assert file_hash(path / 'source.npz') == manifest['source_sha256']
    assert file_hash(path / 'state.npz') == manifest['state_sha256']
    state = load_state(path / 'state.npz')
    with np.load(path / 'source.npz') as source:
        assert source['source_bed_m'].shape == (450, 450)
        assert np.array_equal(source['valid_mask'], state.valid_mask)
        assert not np.any(source['source_ocean'] & source['unknown_wet'])
        assert np.array_equal(source['ocean_seed_mask'], state.ocean_seed_mask)
        ocean = source['source_ocean']
        assert np.all(source['derived_base_bed_m'][ocean] < 0)
        assert np.array_equal(source['derived_base_bed_m'][~ocean], source['source_bed_m'][~ocean])
    assert state.source_identity == manifest['source_identity']
    expected = sum(item['inside_m3'] for item in manifest['crop_inventory'].values())
    actual = sum(getattr(state, name).sum() for name in ('bed_solid_m3', 'mobile_solid_m3', 'stranded_solid_m3'))
    assert np.isclose(actual, expected, rtol=1e-12)
