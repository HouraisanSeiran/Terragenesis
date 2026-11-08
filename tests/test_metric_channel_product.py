from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

from terrain_pipeline.common_infra import file_sha256, identity
from terrain_pipeline.surface_rivers.metric_channel_product import (
    load_channel_product, make_channel_product, sample_channel_output,
    save_channel_product, validate_channel_product, save_channel_output,
    load_channel_output, validate_channel_output,
)
from terrain_pipeline.surface_hydraulics import solve_channel
from terrain_pipeline.channel_geometry import ChannelConfig, ChannelForcing, ChannelNetwork


class _Fixture:
    pass


def closed_fixture():
    network = _Fixture()
    network.receiver = np.array([-1], np.int64)
    network.length_m = np.array([10.])
    network.receiver_distance_m = np.array([0.])
    network.width_m = np.array([2.])
    network.bed_elevation_m = np.array([5.])
    network.bed_slope = np.array([0.])
    network.roughness = np.array([.05])
    network.max_depth_m = np.array([3.])
    network.terminal_kind = np.array(["closed_wall"])
    network.source_identity_sha256 = "a" * 64
    network.section_source = "test-rectangular"
    network.roughness_source = "test-manning"
    forcing = _Fixture()
    forcing.time_seconds = np.array([0., 1., 2.])
    forcing.local_q_m3_s = np.array([[2.], [0.]])
    forcing.source_identity_sha256 = "b" * 64
    result = {"arrays": {
        "time_seconds": np.array([0., 1., 2.]),
        "volume_m3": np.array([[10.], [12.], [12.]]),
        "inflow_q_m3_s": np.zeros((2, 1)),
        "outflow_q_m3_s": np.zeros((2, 1)),
        "local_q_m3_s": np.array([[2.], [0.]]),
        "outflow_end_q_m3_s": np.zeros((3, 1)),
        "depth_m": np.array([[.5], [.6], [.6]]),
        "stage_m": np.array([[5.5], [5.6], [5.6]]),
        "area_m2": np.array([[1.], [1.2], [1.2]]),
        "boundary_outflow_volume_m3": np.zeros((2, 1)),
        "balance_residual_m3": np.zeros((2, 1)),
        "cfl_number": np.zeros(2)},
        "metadata": {"algorithm": "manning-rectangular-explicit-v1", "status": "complete",
                     "failure_reason": None, "requested_end_time_seconds": 2.,
                     "last_time_seconds": 2.,
                     "config": {"max_dt_seconds": 1., "cfl": .8, "max_steps": 100000,
                                "min_dt_seconds": 1e-8}}}
    return network, forcing, result


class ChannelProductTests(unittest.TestCase):
    def test_rehashed_geometry_rejected_in_trace_and_sampled_output(self):
        network = ChannelNetwork(np.array([1, -1], np.int64), np.array([5., 5.]),
            np.ones(2), np.array([1., 0.]), np.full(2, .1), np.full(2, .05),
            np.full(2, 3.), np.array(["interior", "open_outflow"]), "a" * 64,
            "test", "test", receiver_distance_m=np.array([10., 0.]))
        forcing = ChannelForcing(np.array([0., .1]), np.zeros((1, 2)), "b" * 64)
        product = make_channel_product(network, forcing, solve_channel(network, forcing))
        sampled = sample_channel_output(product, np.array([0., .1]))
        for bundle, validator in ((product, validate_channel_product), (sampled, validate_channel_output)):
            self.assertTrue(validator(bundle))
            for bed in ([0., 0.], [0., 1.], [1., .999]):
                altered = deepcopy(bundle)
                altered["arrays"]["network_bed_elevation_m"] = np.array(bed)
                altered["identity_sha256"] = identity(altered["arrays"], altered["metadata"])
                with self.subTest(validator=validator.__name__, bed=bed), self.assertRaisesRegex(ValueError, "downhill|inconsistent"):
                    validator(altered)
            for key, value in (("network_bed_slope", np.array([1., .1])),
                               ("network_receiver_distance_m", np.array([5., 0.]))):
                altered = deepcopy(bundle)
                altered["arrays"][key] = value
                altered["identity_sha256"] = identity(altered["arrays"], altered["metadata"])
                with self.subTest(key=key), self.assertRaisesRegex(ValueError, "inconsistent"):
                    validator(altered)
            altered = deepcopy(bundle)
            altered["arrays"].update(network_receiver=np.array([-1, 0], np.int64),
                network_terminal_kind=np.array(["open_outflow", "interior"]),
                network_receiver_distance_m=np.array([0., 10.]))
            altered["identity_sha256"] = identity(altered["arrays"], altered["metadata"])
            with self.assertRaisesRegex(ValueError, "downhill"):
                validator(altered)
        self.assertEqual(sampled["metadata"]["geometry_semantics"]["open_outflow_slope"],
                         "prescribed_positive_boundary_gradient_no_receiver")

    def test_legacy_geometry_validation_does_not_rewrite_identity(self):
        from terrain_pipeline.surface_rivers.metric_channel_product import LEGACY_SEMANTICS
        network = ChannelNetwork(np.array([1, -1], np.int64), np.full(2, 10.),
            np.ones(2), np.array([1., 0.]), np.full(2, .1), np.full(2, .05),
            np.full(2, 3.), np.array(["interior", "open_outflow"]), "a" * 64, "test", "test")
        forcing = ChannelForcing(np.array([0., .1]), np.zeros((1, 2)), "b" * 64)
        product = make_channel_product(network, forcing, solve_channel(network, forcing))
        sampled = sample_channel_output(product, np.array([0., .1]))
        product["arrays"].pop("network_receiver_distance_m")
        product["metadata"].update(schema="terragenesis-channel-diagnostic-v1", semantics=LEGACY_SEMANTICS)
        sampled["arrays"].pop("network_receiver_distance_m")
        sampled["metadata"].update(schema="terragenesis-channel-output-v1")
        sampled["metadata"].pop("geometry_semantics")
        for bundle, validator in ((product, validate_channel_product), (sampled, validate_channel_output)):
            bundle["identity_sha256"] = identity(bundle["arrays"], bundle["metadata"])
            before = bundle["identity_sha256"]
            self.assertTrue(validator(bundle))
            self.assertEqual(before, identity(bundle["arrays"], bundle["metadata"]))
            bundle["arrays"]["network_length_m"] = np.full(2, 5.)
            bundle["identity_sha256"] = identity(bundle["arrays"], bundle["metadata"])
            with self.assertRaisesRegex(ValueError, "inconsistent"):
                validator(bundle)

    def test_output_resource_budget_rejects_before_state_allocation(self):
        network, forcing, result = closed_fixture()
        product = make_channel_product(network, forcing, result)
        with patch("terrain_pipeline.surface_rivers.metric_channel_product.MAX_BYTES", 1000), patch(
                "terrain_pipeline.surface_rivers.metric_channel_product.np.empty",
                side_effect=AssertionError("sample state allocated")):
            with self.assertRaisesRegex(ValueError, "sampled channel.*budget"):
                sample_channel_output(product, np.linspace(0., 2., 20))

    def test_cold_validator_rejects_rehashed_physics_and_scope_changes(self):
        network = ChannelNetwork(np.array([1, -1], np.int64), np.array([10., 10.]),
                                 np.array([2., 2.]), np.array([5., 4.9]),
                                 np.array([.01, .01]), np.array([.05, .05]),
                                 np.array([3., 3.]), np.array(["interior", "open_outflow"]),
                                 "a" * 64, "test-rectangular", "test-manning")
        forcing = ChannelForcing(np.array([0., 1.]), np.array([[.5, 0.]]), "b" * 64)
        product = make_channel_product(network, forcing,
                                       solve_channel(network, forcing, np.array([10., 5.]),
                                                     ChannelConfig(max_dt_seconds=.1)))
        sampled = sample_channel_output(product, np.array([0., .5, 1.]))
        shifted = deepcopy(sampled)
        shifted["arrays"]["volume_m3"] = shifted["arrays"]["volume_m3"].copy()
        shifted["arrays"]["volume_m3"][1] += np.array([.1, -.1])
        area = shifted["arrays"]["volume_m3"] / network.length_m
        depth = area / network.width_m
        perimeter = network.width_m + 2. * depth
        end_q = area * (area / perimeter) ** (2. / 3.) * np.sqrt(network.bed_slope) / network.roughness
        for key, value in (("area_m2", area), ("depth_m", depth),
                           ("stage_m", network.bed_elevation_m + depth),
                           ("outflow_end_q_m3_s", end_q)):
            shifted["arrays"][key] = value
        shifted["identity_sha256"] = identity(shifted["arrays"], shifted["metadata"])
        with self.assertRaises(ValueError):
            validate_channel_output(shifted)
        changes = (("trace_inflow_q_m3_s", (0, 1), 1.),
                   ("trace_outflow_q_m3_s", (0, 0), 1.),
                   ("trace_cfl_number", (0,), 1.),
                   ("trace_boundary_outflow_volume_m3", (0, 1), 1.),
                   ("trace_time_seconds", (1,), .001))
        for key, cell, delta in changes:
            altered = deepcopy(product)
            altered["arrays"][key] = altered["arrays"][key].copy()
            altered["arrays"][key][cell] += delta
            altered["identity_sha256"] = identity(altered["arrays"], altered["metadata"])
            with self.subTest(key=key), self.assertRaises(ValueError):
                validate_channel_product(altered)
        altered = deepcopy(product)
        altered["metadata"]["publishable"] = True
        altered["identity_sha256"] = identity(altered["arrays"], altered["metadata"])
        with self.assertRaises(ValueError):
            validate_channel_product(altered)
        wrong_algorithm = solve_channel(network, forcing, np.array([10., 5.]),
                                        ChannelConfig(max_dt_seconds=.1))
        wrong_algorithm["metadata"]["algorithm"] = "different-solver"
        with self.assertRaises(ValueError):
            make_channel_product(network, forcing, wrong_algorithm)

    def test_solver_generated_open_outlet_trace_cold_validates(self):
        network = ChannelNetwork(np.array([-1], np.int64), np.array([10.]), np.array([2.]),
                                 np.array([5.]), np.array([.01]), np.array([.05]),
                                 np.array([3.]), np.array(["open_outflow"]),
                                 "a" * 64, "test-rectangular", "test-manning")
        forcing = ChannelForcing(np.array([0., 1.]), np.array([[.5]]), "b" * 64)
        result = solve_channel(network, forcing, np.array([10.]),
                               ChannelConfig(max_dt_seconds=.1))
        product = make_channel_product(network, forcing, result)
        self.assertTrue(validate_channel_product(product))
        sampled = sample_channel_output(product, np.array([0., .25, 1.]))
        self.assertAlmostEqual(sampled["arrays"]["cumulative_boundary_outflow_volume_m3"][-1],
                               product["metadata"]["water_budget_m3"]["boundary_outflow"])

    def test_real_nonzero_failed_prefix_roundtrips(self):
        network = ChannelNetwork(np.array([-1], np.int64), np.array([10.]), np.array([2.]),
                                 np.array([5.]), np.array([0.]), np.array([.05]),
                                 np.array([.5]), np.array(["closed_wall"]),
                                 "a" * 64, "test-rectangular", "test-manning")
        forcing = ChannelForcing(np.array([0., 2.]), np.array([[2.]]), "b" * 64)
        result = solve_channel(network, forcing, np.array([9.]), ChannelConfig(max_dt_seconds=.5))
        self.assertEqual(result["metadata"]["status"], "failed_prefix")
        self.assertGreater(len(result["arrays"]["time_seconds"]), 1)
        product = make_channel_product(network, forcing, result)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "failed.npz"
            save_channel_product(path, product)
            cold = load_channel_product(path, expected_sha256=file_sha256(path),
                                        expected_identity=product["identity_sha256"])
            self.assertEqual(cold["metadata"]["failure_reason"], "depth limit exceeded")

    def test_sampled_output_rejects_rehashed_cycle_and_flat_active_slope(self):
        network, forcing, result = closed_fixture()
        sampled = sample_channel_output(make_channel_product(network, forcing, result), np.array([0., 2.]))
        for key, replacement in (("network_receiver", np.array([0], np.int64)),
                                 ("network_terminal_kind", np.array(["open_outflow"]))):
            altered = deepcopy(sampled)
            altered["arrays"][key] = replacement
            altered["identity_sha256"] = identity(altered["arrays"], altered["metadata"])
            with self.subTest(key=key), self.assertRaises(ValueError):
                validate_channel_output(altered)

    def test_cold_roundtrip_and_arbitrary_sampling_preserve_volume(self):
        network, forcing, result = closed_fixture()
        product = make_channel_product(network, forcing, result)
        dense = sample_channel_output(product, np.array([0., 1., 2.]))
        sparse = sample_channel_output(product, np.array([0., .5, 2.]))
        np.testing.assert_allclose(sparse["arrays"]["volume_m3"][:, 0], [10., 11., 12.])
        np.testing.assert_allclose(sparse["arrays"]["local_q_m3_s"][:, 0], [2., 2. / 3.])
        self.assertEqual(sparse["arrays"]["cumulative_boundary_outflow_volume_m3"][-1],
                         dense["arrays"]["cumulative_boundary_outflow_volume_m3"][-1])
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "channel.npz"
            save_channel_product(path, product)
            loaded = load_channel_product(path, expected_sha256=file_sha256(path),
                                          expected_identity=product["identity_sha256"])
            np.testing.assert_array_equal(loaded["arrays"]["trace_volume_m3"],
                                          product["arrays"]["trace_volume_m3"])
            output_path = Path(folder) / "sample.npz"
            save_channel_output(output_path, sparse)
            loaded_output = load_channel_output(output_path, expected_sha256=file_sha256(output_path),
                                                expected_identity=sparse["identity_sha256"],
                                                expected_product_identity=product["identity_sha256"])
            np.testing.assert_array_equal(loaded_output["arrays"]["volume_m3"],
                                          sparse["arrays"]["volume_m3"])
            altered = deepcopy(sparse)
            altered["arrays"]["cumulative_boundary_outflow_volume_m3"][-1] += 1.
            altered["identity_sha256"] = identity(altered["arrays"], altered["metadata"])
            with self.assertRaises(ValueError):
                validate_channel_output(altered)

    def test_rehashed_tampering_and_zero_step_prefix(self):
        network, forcing, result = closed_fixture()
        product = make_channel_product(network, forcing, result)
        altered = deepcopy(product)
        altered["arrays"]["trace_volume_m3"][1, 0] += 1.
        altered["identity_sha256"] = identity(altered["arrays"], altered["metadata"])
        with self.assertRaises(ValueError):
            validate_channel_product(altered)
        result["arrays"] = {name: (value[:1].copy() if name in
                            ("time_seconds", "volume_m3", "outflow_end_q_m3_s", "depth_m", "stage_m", "area_m2")
                            else value[:0].copy()) for name, value in result["arrays"].items()}
        network.max_depth_m = np.array([.5])
        result["metadata"].update(status="failed_prefix", failure_reason="depth limit exceeded",
                                  last_time_seconds=0.)
        prefix = make_channel_product(network, forcing, result)
        sampled = sample_channel_output(prefix, np.array([0.]))
        np.testing.assert_array_equal(sampled["arrays"]["volume_m3"], [[10.]])
        self.assertEqual(prefix["metadata"]["unfinished_time_seconds"], [0., 2.])

    def test_feasible_shortened_trace_cannot_claim_failed_prefix(self):
        network, forcing, result = closed_fixture()
        product = make_channel_product(network, forcing, result)
        altered = deepcopy(product)
        for key in list(altered["arrays"]):
            if key.startswith("trace_"):
                if (key == "trace_time_seconds" or key.removeprefix("trace_") in
                        ("volume_m3", "outflow_end_q_m3_s", "depth_m", "stage_m", "area_m2")):
                    altered["arrays"][key] = altered["arrays"][key][:2].copy()
                else:
                    altered["arrays"][key] = altered["arrays"][key][:1].copy()
        altered["metadata"].update(status="failed_prefix", failure_reason="depth limit exceeded",
                                   last_time_seconds=1., unfinished_time_seconds=[1., 2.])
        altered["metadata"]["water_budget_m3"] = {
            "initial_storage": 10., "local_input": 2., "boundary_outflow": 0.,
            "final_storage": 12., "residual": 0.}
        altered["identity_sha256"] = identity(altered["arrays"], altered["metadata"])
        with self.assertRaises(ValueError):
            validate_channel_product(altered)


if __name__ == "__main__":
    unittest.main()
