"""Native estuary adapter: sea-bound window, still-sea event, dual budgets."""
import json
from pathlib import Path

import numpy as np
import pytest

from terrain_pipeline.common_infra import file_sha256, json_sha256
from terrain_pipeline.world_process_detail import load_native_terrain, apply_replacements
from terrain_pipeline.world_process_estuary import solve_native_estuary
from terrain_pipeline import world_processes as processes


def coarse_product(*, solid=10.):
    shape = (8, 8)
    bed = np.full(shape, 200.)
    ocean = np.zeros(shape, bool)
    ocean[-1] = True
    bed[-1] = -20.
    arrays = dict(elevation_m=bed.copy(), initial_elevation_m=bed + 1., shaping_initial_elevation_m=bed + 1.,
        discharge_m3_s=np.ones(shape), generation_transported_solid_m3=np.full(shape, solid),
        loose_solid_m3=np.full(shape, 2e5), porosity=np.full(shape, .35), erodibility=np.full(shape, .2),
        ocean_mask=ocean, lake_id=np.zeros(shape, np.int32),
        erosion_m=np.zeros(shape), deposition_m=np.zeros(shape),
        rock_removed_m3=np.zeros(shape), mobile_solid_m3=np.zeros(shape),
        initial_loose_solid_m3=np.full(shape, 2e5), shaping_initial_loose_solid_m3=np.full(shape, 2e5),
        shaping_initial_rock_removed_m3=np.zeros(shape))
    receiver = np.arange(64, dtype=np.int64) + 1
    receiver[-1] = -1
    arrays['receiver'] = receiver.reshape(shape)
    metadata = dict(source_identity='a' * 64, world_seed=20260903, spacing_m=2000., first_xz_m=[1000., 1000.],
        config=dict(shaping_rounds=16, equivalent_exposure_seconds=1e8, rock_reserve_m=1., roughness=.04),
        stages=dict(detailed='pending'),
        solid_budget=dict(initial_loose_solid_m3=float(arrays['loose_solid_m3'].sum()),
            final_loose_solid_m3=float(arrays['loose_solid_m3'].sum()), rock_removed_m3=0.,
            final_mobile_solid_m3=0., marine_received_solid_m3=0., external_dependency_solid_m3=0., residual_m3=0.))
    return dict(arrays=arrays, metadata=metadata, identity='b' * 64, details=[])


def estuary_fixture(tmp_path, *, with_sea=True):
    root = tmp_path / 'native'
    root.mkdir(parents=True, exist_ok=True)
    zz, xx = np.indices((513, 513))
    # Keep the active mouth inside the 8x8 coarse world centered near 3000 m.
    bed = (80. - .05 * (xx - 70) - .08 * (zz - 70)).astype(np.float32)
    if with_sea:
        bed[90:, 40:120] = -5.
        # This nearer closed depression must not become the river's sea inlet.
        bed[80:83, 67:70] = -2.
    np.save(root / 'elevation.npy', bed)
    m = dict(schema='terragenesis-local30-v1', ready=True, plate_identity='a' * 64, world_seed=20260903,
        generator=dict(kind='synthetic-test-fixture-not-model-inference'),
        grid=dict(first_sample_xz_m=[1000., 1000.], spacing_m=30., shape_zx=[513, 513]),
        layers=dict(elevation_m=dict(file='elevation.npy', sha256=file_sha256(root / 'elevation.npy'))))
    m['identity'] = json_sha256(m)
    (root / 'manifest.json').write_text(json.dumps(m), encoding='utf-8')
    return dict(manifest_path=str(root / 'manifest.json'), manifest_sha256=file_sha256(root / 'manifest.json'))


def mouth_region():
    # Native cell ~(70,85) ≈ world (3100, 3550), inside coarse support and above the sea strip.
    return dict(id='mouth', node=55, coarse_support_id='mouth', kind='river_mouth',
                location_xz_m=[1000. + 70 * 30., 1000. + 85 * 30.])


def test_missing_sea_boundary_stays_pending(tmp_path):
    terrain = load_native_terrain(estuary_fixture(tmp_path, with_sea=False), source_identity='a' * 64)
    with pytest.raises(ValueError, match='pending-estuary-driver'):
        solve_native_estuary(coarse_product(), mouth_region(), terrain,
                             config=dict(detail_duration_s=2., estuary_window_cells=32))


def test_still_sea_event_closes_water_and_solid_and_stops_without_sand(tmp_path):
    terrain = load_native_terrain(estuary_fixture(tmp_path), source_identity='a' * 64)
    cfg = dict(detail_duration_s=2., estuary_window_cells=48, max_estuary_cells=48 * 48)
    wet = solve_native_estuary(coarse_product(solid=1e7), mouth_region(), terrain, config=cfg)
    assert wet['status'] == 'complete'
    assert wet['kind'] == 'river_mouth'
    assert wet['hydraulic']['metadata']['status'] == 'complete'
    assert wet['sediment']['metadata']['status'] == 'complete'
    assert wet['budgets']['boundary_water_m3'] == pytest.approx(wet['budgets']['solver_water_input_m3'])
    assert wet['budgets']['boundary_solid_m3'] == pytest.approx(wet['budgets']['solver_external_solid_m3'])
    assert abs(wet['budgets']['water_residual_m3']) < 1e-6 * max(1., wet['budgets']['boundary_water_m3'])
    assert abs(wet['budgets']['solid_residual_m3']) < 1e-5 * max(1., wet['budgets']['boundary_solid_m3'] + 1.)
    assert wet['native_arrays']['final_bed_m'].size <= 48 * 48
    assert wet['metadata']['sea_scenario'] == 'still-sea-mean-0m-no-tide-driver'
    dry = solve_native_estuary(coarse_product(solid=0.), mouth_region(), terrain, config=cfg)
    assert dry['budgets']['solver_external_solid_m3'] == 0.
    assert dry['sediment']['arrays']['external_solid_m3'].sum() == 0.
    # Observe an actual retained/exported solid change, rather than only the
    # existence of a boundary field. Initial finite bed stock is identical.
    wet_stock = wet['budgets']['final_alluvium_and_mobile_solid_m3'] + wet['budgets']['exported_solid_m3']
    dry_stock = dry['budgets']['final_alluvium_and_mobile_solid_m3'] + dry['budgets']['exported_solid_m3']
    assert wet_stock-dry_stock == pytest.approx(wet['budgets']['boundary_solid_m3'], abs=1e-7)
    old = coarse_product(solid=1e7)['arrays']
    revised, consumed = apply_replacements(old, [wet])
    assert consumed == [wet['consumed_package_id']]
    coarse_stock_change = float((revised['loose_solid_m3']-old['loose_solid_m3']).sum()
        +(revised['mobile_solid_m3']-old['mobile_solid_m3']).sum())
    assert coarse_stock_change+wet['budgets']['exported_solid_m3'] == pytest.approx(
        wet['budgets']['solver_external_solid_m3'], abs=1e-7)
    with pytest.raises(ValueError, match='counted twice'):
        apply_replacements(revised, [wet], consumed_package_ids=consumed)
    inlet = int(wet['native_arrays']['inlet_cell'][0])
    shape = tuple(wet['metadata']['window_shape_zx'])
    ocean = wet['native_arrays']['initial_ocean_mask'].reshape(shape)
    row, col = divmod(inlet, shape[1])
    assert any(ocean[r, c] for r, c in ((row-1, col), (row+1, col), (row, col-1), (row, col+1)))
    assert wet['metadata']['inlet_xz_m'][1] == pytest.approx(1000.+89*30.)


def test_closed_negative_depression_touching_crop_is_not_ocean(tmp_path):
    entry = estuary_fixture(tmp_path, with_sea=False)
    path = Path(entry['manifest_path'])
    bed = np.load(path.parent/'elevation.npy')
    bed[50:110, 50:110] = -5.
    np.save(path.parent/'elevation.npy', bed)
    manifest = json.loads(path.read_text(encoding='utf-8'))
    manifest['layers']['elevation_m']['sha256'] = file_sha256(path.parent/'elevation.npy')
    manifest.pop('identity')
    manifest['identity'] = json_sha256(manifest)
    path.write_text(json.dumps(manifest), encoding='utf-8')
    entry['manifest_sha256'] = file_sha256(path)
    terrain = load_native_terrain(entry, source_identity='a'*64)
    with pytest.raises(ValueError, match='ocean connected'):
        solve_native_estuary(coarse_product(), mouth_region(), terrain,
                             config=dict(detail_duration_s=2., estuary_window_cells=32))


def test_replacement_retains_geological_and_environment_bed(tmp_path):
    terrain = load_native_terrain(estuary_fixture(tmp_path), source_identity='a'*64)
    product = coarse_product(solid=1e7)
    product['arrays']['initial_elevation_m'] += 300.
    result = solve_native_estuary(product, mouth_region(), terrain,
        config=dict(detail_duration_s=2., estuary_window_cells=48))
    support = result['support_indices']
    coarse_bed = product['arrays']['elevation_m'].ravel()[support]
    # Shaping was only one metre, despite an unrelated 300m history difference.
    assert np.max(abs(result['replacement_arrays']['elevation_m']-coarse_bed)) < .1
    assert result['replacement_accounting']['coarse_support_transfer_reversal_solid_m3'] == 0.


def test_continue_details_recovers_estuary_driver_failure(tmp_path):
    product = coarse_product()
    product['details'] = [dict(id='mouth', node=55, coarse_support_id='mouth', kind='river_mouth',
        location_xz_m=[1000. + 480 * 30., 1000. + 470 * 30.], status='pending-terrain')]
    processes.save_product(product, tmp_path / 'preview')
    entry = estuary_fixture(tmp_path / 'land', with_sea=False)
    result = processes.continue_details(tmp_path / 'preview', tmp_path / 'fine', terrain_entries=[entry],
                                        config=dict(detail_duration_s=2., estuary_window_cells=32))
    assert result['pending_regions'] == ['mouth']
    detail = processes.query(tmp_path / 'fine')['details'][0]
    assert detail['status'] == 'unresolved'
    assert 'pending-estuary-driver' in detail['reason']
