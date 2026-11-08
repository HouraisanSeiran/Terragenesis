import numpy as np
import pytest

from terrain_pipeline.coastal_delta_evolution import load, save
from terrain_pipeline.coastal_delta_geological_network import construct
from terrain_pipeline.coastal_delta_hydraulics import HydraulicConfig
from terrain_pipeline.coastal_marine_sediment import make_state


def test_network_reuses_sections_and_transfers_only_existing_sediment(tmp_path):
    base = np.full((12, 16), -4.)
    seeds = np.zeros_like(base, bool)
    seeds[:, -1] = True
    state = make_state(base_bed_m=base, bed_solid_m3=10000., mobile_solid_m3=0., porosity=.4,
                       valid_mask=True, ocean_seed_mask=seeds, spacing_m=100.,
                       origin_xz_m=(0., 0.), source_identity='network-test')
    out, progress, hydraulic = construct(state, domain=np.ones_like(base, bool),
        inlet_zx=(6, 1), main_outlet_zx=(6, 14),
        forks=[(0, 2, (2, 14)), (0, 5, (10, 14))], hydraulic_config=HydraulicConfig(10.),
        input_id='network', discharge_m3_s=100., solid_rate_m3_s=.01, depth_m=4., width_m=50.)
    assert progress['route_geometry']['algorithm'] == 'geological-irregular-valley-v1'
    assert len(progress['routes']) == 3
    assert hydraulic['accepted_q_m3_s'] > 0
    assert np.all(out.bed_m >= out.base_bed_m)
    assert np.isclose(out.bed_solid_m3.sum() + out.mobile_solid_m3.sum() + out.unresolved_solid_m3,
                      state.bed_solid_m3.sum())
    save(tmp_path / 'network', out, progress)
    restored, rp = load(tmp_path / 'network')
    assert np.array_equal(restored.bed_solid_m3, out.bed_solid_m3)
    assert rp == progress


def test_width_follows_shared_flow_and_wide_footprint_is_counted_once(tmp_path):
    base = np.full((14, 20), -8.)
    seeds = np.zeros_like(base, bool)
    seeds[:, -1] = True
    state = make_state(base_bed_m=base, bed_solid_m3=12000., mobile_solid_m3=0., porosity=.4,
                       valid_mask=True, ocean_seed_mask=seeds, spacing_m=100.,
                       origin_xz_m=(0., 0.), source_identity='wide-test')
    kwargs = dict(domain=np.ones_like(base, bool), inlet_zx=(7, 1), main_outlet_zx=(7, 18),
                  forks=[(0, 3, (3, 18)), (1, 6, (1, 18)), (0, 7, (12, 18))],
                  hydraulic_config=HydraulicConfig(12.), input_id='network', solid_rate_m3_s=.01,
                  depth_m=8., width_m=100., reference_q_m3_s=100., max_width_m=400., subdivisions=12)
    low, lp, _ = construct(state, discharge_m3_s=100., **kwargs)
    high, hp, flow = construct(state, discharge_m3_s=400., **kwargs)
    low_nodes = {tuple(n[:2]): n for n in lp['hydraulic_sections']['nodes']}
    high_nodes = {tuple(n[:2]): n for n in hp['hydraulic_sections']['nodes']}
    inlet = tuple(hp['routes'][0][0])
    assert high_nodes[inlet][3] > low_nodes[inlet][3]
    assert high_nodes[inlet][3] > state.spacing_m
    last = tuple(hp['routes'][0][-1])
    assert high_nodes[inlet][3] > high_nodes[last][3]
    assert len(hp['geological_network']['forks']) == 3
    assert hp['geological_network']['footprint_area_m2'] > len(high_nodes) * state.spacing_m**2
    owners = hp['integrated']['owner_cells']
    removed_once = sum(state.bed_solid_m3[r, c] * fraction - fine_bed_stock
                       for r, c, fraction, fine_bed_stock, *_ in owners)
    assert np.isclose(removed_once, hp['geological_network']['excavated_solid_m3'])
    assert len({(row[0], row[1]) for row in owners}) == len(owners)
    sections = {tuple(row[:2]): row for row in hp['hydraulic_sections']['nodes']}
    for z, x, parts in hp['node_footprints']:
        expected = sum(state.bed_m[r, c] * fraction for r, c, fraction, *_ in parts) / sum(
            part[2] for part in parts)
        assert sections[(z, x)][4] == pytest.approx(expected)
    assert np.all(high.bed_solid_m3 >= -1e-8)
    assert np.all(high.bed_m >= high.base_bed_m)
    assert np.isclose(high.unresolved_solid_m3, hp['geological_network']['excavated_solid_m3'])
    assert np.isclose(high.bed_solid_m3.sum() + high.mobile_solid_m3.sum() + high.unresolved_solid_m3,
                      state.bed_solid_m3.sum())
    assert flow['accepted_q_m3_s'] > 0
    save(tmp_path / 'wide', high, hp)
    restored, rp = load(tmp_path / 'wide')
    assert rp == hp and np.array_equal(restored.bed_solid_m3, high.bed_solid_m3)
