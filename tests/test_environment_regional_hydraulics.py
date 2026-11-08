from copy import deepcopy
from unittest.mock import patch

import numpy as np
import pytest

from terrain_pipeline import environment_regional_hydraulics as api


def fixture():
    shape = (2, 5)
    receiver = np.array([[1, 2, 3, 4, -1], [6, 7, 8, 9, -1]], np.int64)
    ctx = dict(world_seed=20261020, spacing_m=30., origin_native_xz=[100, 200],
               height_m=np.array([[5., 4., 3., 2., 1.], [5., 4., 3., 2., 1.]]), receiver=receiver,
               source_receiver_node=receiver.copy(), valid_mask=np.ones(shape, bool),
               river_mask=np.ones(shape, bool), protected_mask=np.zeros(shape, bool),
               ocean_mask=np.zeros(shape, bool), node_x_m=np.tile(np.arange(5) * 30., (2, 1)),
               node_z_m=np.repeat(np.arange(2)[:, None] * 30., 5, axis=1))
    return api.prepare_from_context(ctx, {"source_world_identity": "a" * 64}, np.arange(10, dtype=np.int64).reshape(shape))


def assert_equal(left, right):
    assert {k: r["identity_sha256"] for k, r in left.items()} == {k: r["identity_sha256"] for k, r in right.items()}


def test_existing_consumers_conserve_move_and_resume(tmp_path):
    regions = fixture()
    initial = deepcopy(regions)
    with patch.object(api, "solve_channel", wraps=api.solve_channel) as water, patch.object(api, "solve_sediment", wraps=api.solve_sediment) as solid:
        step = api.advance(regions, 2.)
    assert water.call_count == solid.call_count == 2
    assert_equal(regions, initial)
    assert_equal(step, api.advance(regions, 2., request_order=list(reversed(regions))))
    upstream, downstream = sorted(step)
    packet = step[upstream]["metadata"]["exports"][-1]
    assert packet["water_m3"] > 0. and packet["solid_m3"] > 0.
    assert all(len(r["metadata"]["source_nodes"]) == 2 for r in step.values())
    assert step[upstream]["metadata"]["last_solver"]["internal_water_transferred_m3"] > 0.
    assert step[upstream]["metadata"]["last_solver"]["internal_solid_transferred_m3"] > 0.
    assert step[upstream]["arrays"]["bed_m"][0] != regions[upstream]["arrays"]["bed_m"][0]
    assert packet["packet_id"] in step[downstream]["metadata"]["receipts"]
    before_water = sum(r["arrays"]["water_m3"].sum() for r in regions.values())
    after_water = sum(r["arrays"]["water_m3"].sum() for r in step.values())
    terminal = step[downstream]["metadata"]["exports"][-1]
    assert after_water + terminal["water_m3"] == pytest.approx(before_water, abs=1e-10)
    def solid_stock(items):
        return sum(float((r["arrays"]["mobile_solid_m3"] + r["arrays"]["loose_solid_m3"] - r["arrays"]["rock_removed_m3"]).sum()) for r in items.values())
    assert solid_stock(step) + terminal["solid_m3"] == pytest.approx(solid_stock(regions), abs=1e-10)
    path = tmp_path / "checkpoint.npz"
    sha = api.save_checkpoint(path, step)
    cold = api.load_checkpoint(path, expected_sha256=sha)
    assert_equal(step, cold)
    assert api.deliver(cold[downstream], packet)["identity_sha256"] == cold[downstream]["identity_sha256"]
    assert_equal(api.advance(cold, 2.), api.advance(step, 2.))


def test_failure_and_bad_ports_leave_stocks_unchanged():
    regions = fixture()
    initial = deepcopy(regions)
    with pytest.raises(ValueError):
        api.advance(regions, float("nan"))
    step = api.advance(regions, 1.)
    packet = deepcopy(step[sorted(step)[0]]["metadata"]["exports"][-1])
    packet["water_m3"] += 1.
    with pytest.raises(ValueError, match="packet identity"):
        api.deliver(step[sorted(step)[1]], packet)
    assert_equal(regions, initial)


def test_wrong_world_and_time_ports_are_rejected():
    regions = fixture()
    step = api.advance(regions, 1.)
    upstream, downstream = sorted(step)
    packet = deepcopy(step[upstream]["metadata"]["exports"][-1])
    packet["source_world_identity"] = "b" * 64
    packet["packet_id"] = api._digest({k: v for k, v in packet.items() if k != "packet_id"})
    with pytest.raises(ValueError, match="ownership"):
        api.deliver(step[downstream], packet)
    packet = deepcopy(step[upstream]["metadata"]["exports"][-1])
    with pytest.raises(ValueError, match="endpoint"):
        api.deliver(regions[downstream], packet)
