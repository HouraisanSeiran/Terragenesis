import numpy as np
import pytest
from terrain_pipeline.coastal_delta_product import DeltaConfig, advance_formation, load_checkpoint, start, save_checkpoint
from terrain_pipeline.coastal_delta_growth import advance_stage, propose_network

SOURCE = '.scratch/coast-marine-reorganization-20261102/delta-v7-moderate'


def test_shoreline_extension_reworks_only_deposit_and_restarts(tmp_path):
    source, _ = load_checkpoint(SOURCE)
    cfg = DeltaConfig(formation_id='growth-v2-test', inlet_zx=(214, 401),
                      direction_xz=(10200, 1200), clearance_m=1, total_years=40,
                      interval_years=20, solid_rate_m3_s=.08)
    progress = start(source, cfg)
    proposal, excavation, info = propose_network(source, progress, cfg, (213,400))
    assert info['new_endpoint_zx'] != info['old_endpoint_zx']
    cell = tuple(info['new_endpoint_zx'])
    assert cell in excavation and source.base_bed_m[cell] <= excavation[cell]
    invalid = {cell: float(source.base_bed_m[cell])-1}
    with pytest.raises(ValueError, match='finite deposit'):
        advance_formation(source, progress, cfg, network_proposal=proposal, channel_excavation=invalid)
    first, p1, network, _ = advance_stage(source, progress, cfg, (213,400))
    assert tuple(network['branches'][0][-1]) == cell
    assert np.array_equal(first.base_bed_m, source.base_bed_m)
    def total(state):
        return sum(float(getattr(state, name).sum()) for name in
                   ('bed_solid_m3', 'mobile_solid_m3', 'stranded_solid_m3')) + state.exported_solid_m3 + state.unresolved_solid_m3
    assert np.isclose(total(first)-total(source), p1['supply_solid_m3'], atol=1e-5)
    assert p1['channel_treatment'][0]['excavation'][0]['solid_m3'] > 0
    history = p1['growth_history']
    assert history[0]['delivery_leak_multiplier'] == .25
    assert history[0]['mouths_before_zx'][1] != history[0]['mouths_after_zx'][1]
    assert history[0]['excavation'] == p1['channel_treatment'][0]['excavation']
    records = [r for r in first.consumed_packets if r['input_id'] == 'formation:' + cfg.formation_id]
    assert len(records) == 1 and records[0]['formation_progress'] == p1
    save_checkpoint(tmp_path/'growth', first, p1)
    restored, restored_progress = load_checkpoint(tmp_path/'growth')
    continuous, p2, _, _ = advance_stage(first, p1, cfg, (213,400))
    resumed, p3, _, _ = advance_stage(restored, restored_progress, cfg, (213,400))
    assert np.array_equal(continuous.bed_solid_m3, resumed.bed_solid_m3)
    assert np.array_equal(continuous.mobile_solid_m3, resumed.mobile_solid_m3)
    assert p2 == p3
    assert p3['growth_history'][0] == history[0] and len(p3['growth_history']) == 2
    records = [r for r in resumed.consumed_packets if r['input_id'] == 'formation:' + cfg.formation_id]
    assert len(records) == 1 and records[0]['formation_progress'] == p3
    with pytest.raises(ValueError, match='progress'):
        advance_stage(continuous, p1, cfg, (213,400))
