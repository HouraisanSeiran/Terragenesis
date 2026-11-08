from copy import deepcopy
from dataclasses import replace

import numpy as np
import pytest

from terrain_pipeline.coastal_delta_bank_formation import prepare_banks
from terrain_pipeline.coastal_delta_branching import _record
from terrain_pipeline.coastal_delta_evolution import load, save
from terrain_pipeline.coastal_delta_multicell import _prepare
from terrain_pipeline.coastal_delta_node_inventory import ChannelInventory
from test_coastal_delta_multicell import fixture, total


def widened(stage=10.):
    state, progress = fixture()
    state, progress = _prepare(state, progress)
    for key in progress['fixed_channel_footprint']['design_width_m']:
        progress['fixed_channel_footprint']['design_width_m'][key] = 350.
    for row in progress['river_hydraulics']['nodes']:
        row[2] = stage
    return _record(state, progress), progress


def test_claim_conserves_and_restart(tmp_path):
    state, progress = widened(stage=-2.2)
    original = deepcopy(progress)
    out, p, report = prepare_banks(state, progress, max_cut_m=.5)
    assert progress == original
    assert report['added_area_m2'] > 0
    assert report['cut_solid_m3'] > 0
    assert total(out) == pytest.approx(total(state), abs=1e-6)
    assert (state.bed_solid_m3.sum() - out.bed_solid_m3.sum()) == pytest.approx(report['cut_solid_m3'])
    assert out.mobile_solid_m3.sum() - state.mobile_solid_m3.sum() == pytest.approx(report['cut_solid_m3'])
    for field in ('base_bed_m', 'porosity', 'ocean_seed_mask'):
        assert np.array_equal(getattr(out, field), getattr(state, field))
    pool = ChannelInventory(out, p)
    assert pool._fractions.max() <= 1 + 1e-10
    assert report['effective_area_after_m2'] - report['effective_area_before_m2'] == pytest.approx(report['added_area_m2'])
    save(tmp_path / 'bank', out, p)
    restored, rp = load(tmp_path / 'bank')
    assert rp == p
    assert np.array_equal(restored.bed_solid_m3, out.bed_solid_m3)
    again, ap, second = prepare_banks(restored, rp, max_cut_m=.5)
    assert second['added_area_m2'] == pytest.approx(0.)
    assert np.allclose(again.bed_solid_m3, restored.bed_solid_m3, rtol=0, atol=1e-9)


def test_high_bank_and_missing_stage_are_not_claimed():
    state, p = widened(stage=-20.)
    out, result, report = prepare_banks(state, p)
    assert report['added_area_m2'] == 0
    assert any('bank_above_wet_limit' in row['rejected_area_m2'] for row in report['nodes'].values())
    assert np.allclose(state.bed_solid_m3, out.bed_solid_m3, rtol=0, atol=1e-9)
    p = deepcopy(p)
    p['river_hydraulics']['nodes'] = []
    state = _record(state, p)
    _, _, report = prepare_banks(state, p)
    assert report['added_area_m2'] == 0
    assert any('missing_stage' in row['rejected_area_m2'] for row in report['nodes'].values())


def test_free_area_competition_preserves_old_parts(monkeypatch):
    state, p = widened()
    before = deepcopy(p['node_footprints'])
    nodes = [tuple(row[:2]) for row in before[:2]]
    cell = (0, 0)
    def desired(*args):
        return nodes, None, None, None, None, None, [[[0, 0, .8, 0]], [[0, 0, .8, 0]]]
    monkeypatch.setattr('terrain_pipeline.coastal_delta_bank_formation._footprint', desired)
    out, result, report = prepare_banks(state, p)
    pool = ChannelInventory(out, result)
    assert pool._fractions[cell] == pytest.approx(1.)
    assert [report['nodes'][str(n)]['added_area_m2'] for n in nodes] == pytest.approx([5000., 5000.])
    for old, new in zip(before, result['node_footprints']):
        assert new[2][:len(old[2])] == old[2]
    assert sum(part[3] for parts in pool._parts.values() for part in parts if tuple(part[:2]) == cell) == pytest.approx(state.bed_solid_m3[cell])
    _, _, second = prepare_banks(out, result)
    assert second['added_area_m2'] == 0
    assert any('no_free_area' in d['rejected_area_m2'] for d in second['nodes'].values())

