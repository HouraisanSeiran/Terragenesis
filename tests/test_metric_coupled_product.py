from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

from terrain_pipeline.mountain_source_adapter import file_sha256, identity
from terrain_pipeline.surface_rivers.metric_channel_state import ChannelConfig, ChannelNetwork
from terrain_pipeline.surface_rivers.metric_lake_storage import LakeStorage, LakeOutlet
from terrain_pipeline.surface_rivers.metric_boundary_coupling import BoundarySeries, CoupledForcing, solve_coupled
from terrain_pipeline.surface_rivers.metric_coupled_product import (
    make_coupled_product, load_coupled_product, save_coupled_product, sample_coupled_output, validate_coupled_product,
)


def fixture():
    network = ChannelNetwork(np.array([-1, -1], np.int64), np.full(2, 10.), np.full(2, 2.),
                             np.array([2., 0.]), np.full(2, .01), np.full(2, .04), np.full(2, 5.),
                             np.array(["open_outflow", "open_outflow"]), "a" * 64, "explicit section", "explicit n")
    lake = LakeStorage(np.array([12, 13], np.int64), np.array([0., .5]), np.array([5., 5.]),
                       12, 3., "b" * 64, "finite_pool_vertical_wall")
    outlets = (LakeOutlet(0, 1, 1., .8, "explicit weir coefficient"),)
    times = np.array([0., 20., 60.])
    forcing = CoupledForcing(times, np.array([[.2, 0.], [0., 0.]]), np.zeros((2, 1)), "c" * 64)
    boundaries = BoundarySeries(np.empty(0, np.int64), np.empty(0, "U24"), np.empty(0, bool), times,
                                np.empty((2, 0)), np.empty((2, 0)), np.empty(0), "d" * 64)
    mapping = np.array([0, -1], np.int64)
    result = solve_coupled(network, (lake,), outlets, mapping, forcing, boundaries,
                           initial_lake_volume_m3=np.array([7.4]), config=ChannelConfig(max_dt_seconds=.1))
    return network, (lake,), outlets, mapping, forcing, boundaries, result


class CoupledProductTests(unittest.TestCase):
    def test_cold_roundtrip_and_sparse_sampling_preserve_exchange_budget(self):
        product = make_coupled_product(*fixture())
        dense = sample_coupled_output(product, np.arange(0., 61., 1.))
        sparse = sample_coupled_output(product, np.array([0., 60.]))
        for name in ("channel_volume_m3", "lake_volume_m3", "cumulative_channel_boundary_volume_m3", "cumulative_lake_external_volume_m3"):
            np.testing.assert_array_equal(dense["arrays"][name][-1], sparse["arrays"][name][-1])
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "coupled.npz"
            save_coupled_product(path, product)
            with patch("terrain_pipeline.surface_rivers.metric_boundary_coupling.solve_coupled", side_effect=AssertionError("cold called solver")):
                loaded = load_coupled_product(path, expected_sha256=file_sha256(path), expected_identity=product["identity_sha256"])
            self.assertEqual(loaded["identity_sha256"], product["identity_sha256"])

    def test_rehashed_exchange_and_scope_tampering_rejects(self):
        product = make_coupled_product(*fixture())
        changes = (("trace_lake_donor_q_m3_s", (10, 0)), ("trace_channel_boundary_volume_m3", (10, 0)),
                   ("trace_lake_outlet_q_m3_s", (10, 0)), ("trace_channel_residual_m3", (10, 0)))
        for key, position in changes:
            altered = deepcopy(product)
            altered["arrays"][key] = altered["arrays"][key].copy()
            altered["arrays"][key][position] += .1
            altered["identity_sha256"] = identity(altered["arrays"], altered["metadata"])
            with self.subTest(key=key), self.assertRaises(ValueError):
                validate_coupled_product(altered)
        altered = deepcopy(product)
        altered["metadata"]["publishable"] = True
        altered["identity_sha256"] = identity(altered["arrays"], altered["metadata"])
        with self.assertRaises(ValueError):
            validate_coupled_product(altered)

    def test_prefix_failure_reason_requires_actual_next_failure(self):
        arguments = list(fixture())
        result = arguments[-1]
        # A correct first step is feasible to continue, so a claimed depth refusal is false.
        result["arrays"] = {name: value[:2].copy() if name in (
            "time_seconds", "channel_volume_m3", "lake_volume_m3", "channel_stage_m", "lake_stage_m")
            else value[:1].copy() for name, value in result["arrays"].items()}
        result["metadata"].update(status="failed_prefix", last_time_seconds=float(result["arrays"]["time_seconds"][-1]),
                                  failure_reason="lake capacity exceeded")
        with self.assertRaises(ValueError):
            make_coupled_product(*arguments)


if __name__ == "__main__":
    unittest.main()
