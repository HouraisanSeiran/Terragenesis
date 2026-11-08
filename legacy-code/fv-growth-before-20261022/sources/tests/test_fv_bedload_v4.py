from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path

import numpy as np
import pytest

from tests.test_fv_suspended_growth import geometry, packet
from terrain_pipeline.surface_rivers import metric_fv_bedload_v4 as v4
from terrain_pipeline.surface_rivers.metric_fv_coastal_sediment import BedloadConfig, transport_bedload as frozen_transport
from tools import run_natural_fv_growth_v4 as runner
from tools.inspect_natural_fv_growth import audit_carrier_chunk


def water(g, volume=1., dt=.1):
    p = packet(g, dt)
    p.update(momentum_before=np.tile([.5, 0.], (9, 1)), momentum_after=np.tile([.5, 0.], (9, 1)),
        tailwater_m=np.full(len(g["arrays"]["boundary_cell"]), .5))
    p["internal_transfer_m3"][:] = volume
    return p


def test_same_reverse_zero_carrier_inventory_and_boundary_conserve(monkeypatch):
    g = geometry()
    a = g["arrays"]
    a["boundary_kind"][:] = 2
    p = water(g)
    p["internal_transfer_m3"][:3] = [1., -1., 0.]
    p["boundary_transfer_m3"][:] = .1
    p["boundary_transfer_m3"][0] = -.1

    def requested(velocity, orbital, depth, config):
        return np.full_like(velocity, 10.)

    monkeypatch.setattr(v4, "_phase_averaged_mpm", requested)
    bed = a["H2_m"].copy()
    floor = bed - .0001
    config = BedloadConfig(wave_height_m=0., max_bed_change_m=1.)
    result = v4.transport_bedload(bed, floor, g, p, config)
    accepted = result["carrier_internal_accepted_solid_m3"]
    np.testing.assert_allclose(accepted[:3], [.65, 0., 0.])
    assert result["carrier_boundary_accepted_solid_m3"][0] == 0.
    assert result["ledger"]["carrier_direction_rejected_faces"] == 2
    assert result["ledger"]["inventory_limited_donors"] > 0
    assert np.min(result["bed_m"] - floor) >= -1.e-12
    assert result["ledger"]["residual_solid_m3"] == pytest.approx(0., abs=1.e-12)
    assert result["ledger"]["exported_solid_m3"] > 0.
    assert np.all(abs(result["internal_transfer_solid_m3"]) <= .65 * abs(p["internal_transfer_m3"]))


def test_normal_deep_water_mpm_requests_remain_unchanged():
    g = geometry()
    p = water(g, volume=.25)
    config = BedloadConfig(wave_height_m=.3, max_bed_change_m=1.)
    bed = g["arrays"]["H2_m"]
    floor = bed - .3
    expected = frozen_transport(bed, floor, g, p, config)
    result = v4.transport_bedload(bed, floor, g, p, config)
    assert result["ledger"]["carrier_capacity_limited_faces"] == 0
    assert result["ledger"]["carrier_direction_rejected_faces"] == 0
    np.testing.assert_allclose(result["internal_transfer_solid_m3"], expected["internal_transfer_solid_m3"], rtol=1.e-13, atol=1.e-15)
    np.testing.assert_allclose(result["bed_m"], expected["bed_m"], rtol=0., atol=1.e-14)


def test_real_refused_thin_bank_packet_obeys_finite_carrier():
    path = Path("verification/fluvial-delta/natural-fv-v3-mpm-rejection-20261019-01/rejected-input-and-proposal.npz")
    if not path.exists():
        pytest.skip("local production refusal witness unavailable")
    with np.load(path, allow_pickle=False) as d:
        g = {"arrays": {k[9:]: d[k] for k in d.files if k.startswith("geometry_")}, "metadata": {"spacing_m": 5.}}
        p = {k[7:]: d[k] for k in d.files if k.startswith("packet_")}
        config = BedloadConfig(wave_height_m=.3)
        result = v4.transport_bedload(d["bed_m"], d["floor_m"], g, p, config)
        face = 10146
        assert result["mpm_internal_requested_solid_m3"][face] == pytest.approx(-.168298700184995, rel=1.e-12)
        assert result["internal_transfer_solid_m3"][face] == pytest.approx(.65 * p["internal_transfer_m3"][face], rel=1.e-12)
        assert abs(result["internal_transfer_solid_m3"][face]) < 1.6e-6
        assert result["ledger"]["maximum_abs_bed_change_m"] < .01
        assert abs(result["ledger"]["residual_solid_m3"]) < 1.e-8


def test_actual_fv_runner_restart_preserves_state_cursor_and_v4_identity(tmp_path):
    g = geometry()
    bed = g["arrays"]["H2_m"].copy()
    types = np.zeros_like(bed, dtype=int)
    types[0] = 1
    data = {"bed_m": bed, "initial_bed_m": bed.copy(), "source_floor_m": bed - .3,
        "cell_type": types, "local_world_xz_m": np.zeros((*bed.shape, 2)),
        "fixed_boundary_mask": np.zeros_like(bed, bool), "depth_m": np.ones_like(bed),
        "momentum_m2_s": np.tile([.05, .02], (9, 1)), "suspended_solid_m3": np.zeros_like(bed),
        "source_schedule": np.array([[0., 0., 10., .02, 20., 100.]])}
    meta = {"physical_time_s": 0., "source_cursor_s": 0., "cumulative_injected_solid_m3": 0.,
        "cumulative_exported_solid_m3": 0., "source_total_solid_m3": .02}
    initial = tmp_path / "initial.npz"
    runner.save_checkpoint(initial, data, meta)
    args = runner.parser().parse_args(["--resume", str(initial), "--output", str(tmp_path / "one"),
        "--duration-s", ".0625", "--interval-s", ".0625", "--wave-height", ".3", "--river-q", "1"])
    first = runner.run(args)
    args.resume = Path(first["checkpoint"])
    args.output = tmp_path / "two"
    second = runner.run(args)
    state, checkpoint = runner.load_checkpoint(Path(second["checkpoint"]))
    assert checkpoint["schema"] == "finite-FV-growth-checkpoint-v4"
    assert checkpoint["implementation_hashes"] == runner.identities()
    assert checkpoint["bedload_transport_contract"] == runner.CONTRACT
    assert checkpoint["physical_time_s"] == .125
    assert checkpoint["source_cursor_s"] == .125
    assert second["schema"] == "finite-FV-suspended-growth-v4"
    assert abs(second["combined_residual_solid_m3"]) < 1.e-9
    assert abs(second["water_volume_residual_m3"]) < 1.e-9
    with np.load(args.output / "result.npz") as result, np.load(first["checkpoint"]) as before:
        for key in runner.previous.STATE:
            np.testing.assert_array_equal(result[key][0], before[key])
    with np.load(next(args.output.glob("chunk-audit-*.npz"))) as audit:
        assert "bedload_mpm_internal_requested_solid_m3" in audit.files
        arrays = {key: audit[key] for key in audit.files}
        assert audit_carrier_chunk(arrays)["maximum_carrier_violation_solid_m3"] == 0.
        missing = dict(arrays)
        del missing["bedload_carrier_internal_max_direction_violation_solid_m3"]
        with pytest.raises(ValueError, match="mandatory carrier"):
            audit_carrier_chunk(missing)
        arrays["bedload_carrier_internal_max_direction_violation_solid_m3"] = np.asarray(.01)
        assert audit_carrier_chunk(arrays)["maximum_carrier_violation_solid_m3"] == .01
    assert list((args.output / "packets").glob("*-carrier.npz"))
