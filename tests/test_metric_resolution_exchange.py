import json
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
import numpy as np
from terrain_pipeline.common_infra import file_sha256, identity
from terrain_pipeline.surface_rivers.metric_channel_product import LEGACY_SEMANTICS, make_channel_product, save_channel_product
from terrain_pipeline.surface_hydraulics import solve_channel
from terrain_pipeline.channel_geometry import ChannelConfig, ChannelForcing, ChannelNetwork
from terrain_pipeline.surface_rivers.metric_resolution_exchange import audit_comparison, refine_channel, restrict_inventory, run_resolution_comparison


class ResolutionExchangeTests(unittest.TestCase):
    def test_saved_v1_native_basis_upgrades_without_changing_numerical_identity(self):
        net, _ = self.scenario()
        forcing = ChannelForcing(np.array([0., .1]), np.array([[.1, .2, .3]]), "b" * 64)
        config = ChannelConfig(max_dt_seconds=.05)
        current = make_channel_product(net, forcing, solve_channel(net, forcing, config=config))
        legacy = deepcopy(current)
        legacy["arrays"].pop("network_receiver_distance_m")
        legacy["metadata"].update(schema="terragenesis-channel-diagnostic-v1", semantics=LEGACY_SEMANTICS)
        legacy["identity_sha256"] = identity(legacy["arrays"], legacy["metadata"])
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            source_path = folder / "saved-m3.npz"
            acceptance_path = folder / "acceptance.json"
            acceptance_path.write_text("{}", encoding="utf-8")
            save_channel_product(source_path, legacy)
            source_sha = file_sha256(source_path)
            source_manifest = {
                "native_channel_product": {"path": str(source_path), "sha256": source_sha,
                    "identity_sha256": legacy["identity_sha256"]},
                "acceptance_path": str(acceptance_path), "acceptance_sha256": file_sha256(acceptance_path)}
            comparison_path = folder / "comparison.json"
            payload = run_resolution_comparison(net, forcing, local_counts=np.array([1, 2, 1]),
                output_path=comparison_path, source_manifest=source_manifest, config=config)
            self.assertNotEqual(legacy["identity_sha256"], payload["cases"]["native"]["channel_trace"]["identity_sha256"])
            self.assertEqual(audit_comparison(comparison_path)["status"], "accepted_conservative_1d_exchange")
            self.assertEqual(file_sha256(source_path), source_sha)
            for basis in (legacy, current):
                changed = deepcopy(basis)
                changed["metadata"]["config"]["max_steps"] += 1
                changed["identity_sha256"] = identity(changed["arrays"], changed["metadata"])
                changed_path = folder / (basis["metadata"]["schema"] + ".npz")
                save_channel_product(changed_path, changed)
                payload["source_manifest"]["native_channel_product"] = {
                    "path": str(changed_path),
                    "sha256": file_sha256(changed_path),
                    "identity_sha256": changed["identity_sha256"]}
                comparison_path.write_text(json.dumps(payload), encoding="utf-8")
                with self.subTest(schema=basis["metadata"]["schema"]), self.assertRaisesRegex(ValueError, "pinned M3 volume basis"):
                    audit_comparison(comparison_path)

    def test_refinement_uses_receiver_distance_not_storage_control_length(self):
        from dataclasses import replace
        net, forcing = self.scenario()
        net = replace(net, length_m=np.array([5., 10., 5.]),
                      receiver_distance_m=np.array([10., 10., 0.]))
        case = refine_channel("split_control", net, forcing, np.array([2, 2, 2]))
        np.testing.assert_allclose(case.network.length_m, [2.5, 2.5, 5., 5., 2.5, 2.5])
        np.testing.assert_allclose(case.network.receiver_distance_m, [5., 5., 5., 5., 2.5, 0.])
        np.testing.assert_allclose(case.network.bed_elevation_m, [3., 2.5, 2., 1.5, 1., .75])
        np.testing.assert_allclose(restrict_inventory(case.network.length_m, case.parent_index, 3), net.length_m)

    def scenario(self, terminal="open_outflow"):
        net = ChannelNetwork(np.array([1, 2, -1], np.int64), np.full(3, 10.), np.full(3, 2.),
            np.array([3., 2., 1.]), np.full(3, .1), np.full(3, .035), np.full(3, 10.),
            np.array(["interior", "interior", terminal]), "a" * 64, "test", "test")
        forcing = ChannelForcing(np.array([0., 2., 6.]), np.array([[.1, .2, .3], [0., 0., 0.]]), "b" * 64)
        return net, forcing

    def test_actual_mixed_refinement_and_shared_flux(self):
        net, forcing = self.scenario()
        case = refine_channel("local_amr", net, forcing, np.array([1, 2, 1]))
        np.testing.assert_array_equal(case.network.receiver, [1, 2, 3, -1])
        np.testing.assert_array_equal(case.network.length_m, [10., 5., 5., 10.])
        np.testing.assert_array_equal(case.network.bed_elevation_m, [3., 2., 1.5, 1.])
        np.testing.assert_allclose(restrict_inventory(case.forcing.local_q_m3_s, case.parent_index, 3), forcing.local_q_m3_s)
        result = solve_channel(case.network, case.forcing)
        np.testing.assert_array_equal(result["arrays"]["inflow_q_m3_s"][:, 1:], result["arrays"]["outflow_q_m3_s"][:, :-1])
        self.assertEqual(result["metadata"]["status"], "complete")

    def test_unknown_and_closed_terminal_are_preserved(self):
        for terminal in ("unknown_boundary", "closed_wall"):
            net, forcing = self.scenario(terminal)
            case = refine_channel("uniform", net, forcing, np.array([2, 2, 2]))
            self.assertEqual(case.network.terminal_kind[-1], terminal)
            self.assertEqual(np.count_nonzero(case.network.receiver == -1), 1)
            result = solve_channel(case.network, case.forcing)
            self.assertEqual(float(result["arrays"]["boundary_outflow_volume_m3"].sum()), 0.)
            self.assertAlmostEqual(float(result["arrays"]["volume_m3"][-1].sum()), 1.2)

    def test_zero_slope_terminals_remain_one_control(self):
        from dataclasses import replace
        for terminal in ("unknown_boundary", "closed_wall"):
            net, forcing = self.scenario(terminal)
            net = replace(net, bed_slope=np.array([.1, .1, 0.]))
            case = refine_channel("uniform", net, forcing, np.array([2, 2, 2]))
            np.testing.assert_array_equal(case.counts, [2, 2, 1])
            result = solve_channel(case.network, case.forcing)
            self.assertEqual(result["metadata"]["status"], "complete")
            self.assertEqual(float(result["arrays"]["boundary_outflow_volume_m3"].sum()), 0.)

    def test_zero_interval_failed_prefix_is_saved(self):
        net, forcing = self.scenario()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "comparison.json"
            # A stronger fixed source exceeds the capacity before the first commit.
            forcing = ChannelForcing(np.array([0., 100.]), np.full((1, 3), 100.), "b" * 64)
            report = run_resolution_comparison(net, forcing, local_counts=np.array([1, 2, 1]), output_path=path, source_manifest={}, config=ChannelConfig(max_dt_seconds=100.))
            self.assertEqual(report["cases"]["uniform"]["resource"]["steps"], 0)
            self.assertIsNone(report["cases"]["uniform"]["sediment_trace"])
            self.assertEqual(audit_comparison(path)["cases"]["uniform"]["sediment_status"], "not_run")
            self.assertIsNone(report["cases"]["uniform"]["native_bed_change_m"])

    def test_sediment_archive_overhead_does_not_consume_payload_budget(self):
        from unittest.mock import patch
        from terrain_pipeline.surface_rivers.metric_sediment import load_sediment
        net, forcing = self.scenario()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "comparison.json"
            report = run_resolution_comparison(net, forcing, local_counts=np.array([1, 2, 1]), output_path=path, source_manifest={})
            pin = report["cases"]["native"]["sediment_trace"]
            bundle = load_sediment(path.parent / pin["path"], expected_sha256=pin["sha256"])
            payload_bytes = sum(v.nbytes for v in bundle["arrays"].values())
            with patch("terrain_pipeline.surface_rivers.metric_sediment.MAX_BYTES", payload_bytes):
                loaded = load_sediment(path.parent / pin["path"], expected_sha256=pin["sha256"])
            self.assertEqual(loaded["identity_sha256"], pin["identity_sha256"])

    def test_real_water_solid_cold_audit_and_tampered_mapping(self):
        net, forcing = self.scenario()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "comparison.json"
            payload = run_resolution_comparison(net, forcing, local_counts=np.array([1, 2, 1]), output_path=path, source_manifest={}, config=ChannelConfig(max_dt_seconds=.5))
            audit = audit_comparison(path)
            self.assertEqual(audit["status"], "accepted_conservative_1d_exchange")
            self.assertEqual(len(audit["cases"]["local_amr"]["mixed_interfaces"]), 2)
            payload["cases"]["local_amr"]["parent_index"][1] = 0
            path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "mapping"):
                audit_comparison(path)

    def test_same_step_budget_preserves_failed_prefixes(self):
        net, forcing = self.scenario()
        with tempfile.TemporaryDirectory() as directory:
            payload = run_resolution_comparison(net, forcing, local_counts=np.array([1, 2, 1]), output_path=Path(directory) / "comparison.json", source_manifest={}, config=ChannelConfig(max_dt_seconds=.5, max_steps=2))
            for report in payload["cases"].values():
                self.assertEqual(report["status"], "failed_prefix")
                self.assertEqual(report["failure_reason"], "maximum step count exceeded")


if __name__ == "__main__":
    unittest.main()
