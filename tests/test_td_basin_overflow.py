import unittest
import json

import numpy as np

from terrain_pipeline.td_basin_source import make_td_source
from terrain_pipeline.td_basin_hierarchy import build_basin_hierarchy
from terrain_pipeline.td_basin_overflow import (
    OverflowParameters, add_saved_overflow_accounting, build_overflow_topology, load_overflow_event, save_overflow_event,
    save_overflow_topology, simulate_overflow, validate_overflow_event,
)
from terrain_pipeline.mountain_source_adapter import file_sha256, identity
from tools.audit_td_original_bed_overflow import audit_saved_arrays
from tools.export_td_overflow_accounting import export
from pathlib import Path
import tempfile
from unittest.mock import patch


class BasinOverflowTests(unittest.TestCase):
    def fixture(self):
        hierarchy = build_basin_hierarchy(make_td_source(np.array([[0., 1., 0.], [0., 1., 0.]]), spacing_m=1.))
        topology = build_overflow_topology(hierarchy)
        event = simulate_overflow(topology, np.full(12, 12000.),
                                  parameters=OverflowParameters(timestep_s=300., duration_s=3600.))
        return topology, event

    def copied_event(self, event):
        return {"arrays": {name: value.copy() for name, value in event["arrays"].items()},
                "metadata": dict(event["metadata"]), "identity_sha256": event["identity_sha256"]}

    def test_per_basin_budget_and_independent_original_bed_stage(self):
        topology, event = self.fixture()
        arrays = event["arrays"]
        np.testing.assert_allclose(np.diff(arrays["volume_m3"], axis=0),
                                   arrays["input_volume_m3"] + arrays["basin_net_internal_m3"] - arrays["basin_boundary_outflow_m3"], atol=1e-9)
        report = audit_saved_arrays(topology, event)
        self.assertLess(report["max_abs_basin_residual_m3"], 1e-7)
        self.assertLess(report["max_stage_inversion_error_m"], 1e-8)
        self.assertAlmostEqual(report["gross_exchange_m3"], report["canceled_bidirectional_exchange_m3"] + report["sum_absolute_cumulative_face_net_m3"])
        self.assertGreater(report["bidirectional_face_count"], 0)

    def test_global_conservation_cannot_hide_wrong_basin_inventory(self):
        topology, event = self.fixture()
        changed = self.copied_event(event)
        changed["arrays"]["volume_m3"][-1, 0] += .01
        changed["arrays"]["volume_m3"][-1, 1] -= .01
        changed["identity_sha256"] = identity(changed["arrays"], changed["metadata"])
        with self.assertRaisesRegex(ValueError, "basin storage closure"):
            validate_overflow_event(changed, topology)
        with self.assertRaisesRegex(ValueError, "per-basin inventory"):
            audit_saved_arrays(topology, changed)

    def test_rehashed_net_ledger_and_nonfinite_values_are_rejected(self):
        topology, event = self.fixture()
        for field in ("face_net_m3", "basin_net_internal_m3", "basin_gross_internal_m3",
                      "basin_boundary_outflow_m3", "basin_balance_residual_m3"):
            with self.subTest(field=field):
                changed = self.copied_event(event)
                changed["arrays"][field].flat[0] += .01
                changed["identity_sha256"] = identity(changed["arrays"], changed["metadata"])
                with self.assertRaises(ValueError):
                    validate_overflow_event(changed, topology)
        changed = self.copied_event(event)
        changed["arrays"]["volume_m3"].flat[0] = np.nan
        changed["identity_sha256"] = identity(changed["arrays"], changed["metadata"])
        with self.assertRaisesRegex(ValueError, "nonfinite"):
            validate_overflow_event(changed, topology)

    def test_audit_rejects_wrong_stage_and_forcing_without_solver(self):
        topology, event = self.fixture()
        for field, message in (("stage_m", "storage/stage"), ("rain_mm_h", "rainfall input")):
            changed = self.copied_event(event)
            changed["arrays"][field].flat[0] += .01
            with self.assertRaisesRegex(ValueError, message):
                audit_saved_arrays(topology, changed)

    def test_v1_cold_read_upgrade_keeps_saved_physics_unchanged(self):
        topology, event = self.fixture()
        legacy = self.copied_event(event)
        for field in ("face_net_m3", "basin_net_internal_m3", "basin_gross_internal_m3",
                      "basin_boundary_outflow_m3", "basin_balance_residual_m3"):
            del legacy["arrays"][field]
        legacy["metadata"].update(schema="td-original-bed-overflow-event-v1", algorithm="synchronous-basin-face-exchange-v1")
        del legacy["metadata"]["flux_semantics"]
        legacy["identity_sha256"] = identity(legacy["arrays"], legacy["metadata"])
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "legacy.json"
            save_overflow_event(legacy, path)
            with patch("terrain_pipeline.td_basin_overflow.simulate_overflow", side_effect=AssertionError("solver forbidden")):
                loaded = load_overflow_event(path, expected_sha256=file_sha256(path), expected_identity=legacy["identity_sha256"], topology=topology)
                upgraded = add_saved_overflow_accounting(loaded, topology)
            for name, values in legacy["arrays"].items():
                np.testing.assert_array_equal(upgraded["arrays"][name], values)
            self.assertEqual(upgraded["identity_sha256"], event["identity_sha256"])
            audit_saved_arrays(topology, loaded)

    def test_diagnostic_flags_and_onset_cannot_be_forged(self):
        topology, event = self.fixture()
        for flag in ("hydraulic_ready", "transient_converged", "natural_outlet_verified", "publishable"):
            changed = self.copied_event(event)
            changed["metadata"][flag] = True
            changed["identity_sha256"] = identity(changed["arrays"], changed["metadata"])
            with self.assertRaises(ValueError):
                validate_overflow_event(changed, topology)
        changed = self.copied_event(event)
        changed["arrays"]["spill_onset_step"].fill(-1)
        changed["identity_sha256"] = identity(changed["arrays"], changed["metadata"])
        with self.assertRaises(ValueError):
            validate_overflow_event(changed, topology)

    def test_accounting_package_export_is_cold_pinned_and_no_overwrite(self):
        topology, event = self.fixture()
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            source_path = directory / "source-pin.json"
            source_path.write_text("{}", encoding="utf-8")
            topology_path = directory / "original-bed-overflow-topology.json"
            event_path = directory / "event.json"
            save_overflow_topology(topology, topology_path)
            save_overflow_event(event, event_path)
            index_path = directory / "index.json"
            index_path.write_text(json.dumps({
                "input_pins": {"source": {"path": str(source_path), "sha256": file_sha256(source_path)}},
                "summary": {"leaf_count": len(topology["arrays"]["leaf_ids"])},
                "topology": {"path": str(topology_path), "sha256": file_sha256(topology_path), "identity_sha256": topology["identity_sha256"]},
                "cases": [{"name": "fixture", "event": {"path": str(event_path), "sha256": file_sha256(event_path)},
                           "event_identity_sha256": event["identity_sha256"]}]}), encoding="utf-8")
            output = directory / "exported"
            with patch("terrain_pipeline.td_basin_overflow.simulate_overflow", side_effect=AssertionError("solver forbidden")):
                result = export(index_path, expected_index_sha256=file_sha256(index_path), output=output)
            self.assertFalse(result["event_model_advanced"])
            self.assertEqual(result["cases"][0]["event_identity_sha256"], event["identity_sha256"])
            with self.assertRaises(FileExistsError):
                export(index_path, expected_index_sha256=file_sha256(index_path), output=output)
            with self.assertRaises(ValueError):
                export(index_path, expected_index_sha256="0" * 64, output=directory / "rejected")
            self.assertFalse((directory / "rejected").exists())

    def test_closed_basin_stores_until_sill_then_exchanges(self):
        height = np.array([[0., 2., 0.], [0., 2., 0.]])
        hierarchy = build_basin_hierarchy(make_td_source(height, spacing_m=1.))
        topology = build_overflow_topology(hierarchy, expected_hierarchy_identity=hierarchy["identity_sha256"])
        event = simulate_overflow(topology, np.full(12, 12000.0), parameters=OverflowParameters(timestep_s=300., duration_s=3600.))
        validate_overflow_event(event, topology)
        self.assertTrue(np.all(np.abs(event["arrays"]["balance_residual_m3"]) < 1e-7))
        self.assertGreater(np.sum(event["arrays"]["face_volume_m3"]), 0.)
        self.assertTrue(np.any(event["arrays"]["spill_onset_step"] >= 0))
        self.assertFalse(event["metadata"]["natural_outlet_verified"])
        self.assertEqual(event["metadata"]["schema"], "td-original-bed-overflow-event-v2")
        self.assertTrue(np.allclose(event["arrays"]["face_net_m3"], event["arrays"]["face_forward_m3"] - event["arrays"]["face_reverse_m3"]))
        self.assertTrue(np.allclose(event["arrays"]["basin_net_internal_m3"].sum(axis=1), 0.))

    def test_bidirectional_face_ledger_is_separate_and_conservative(self):
        height = np.array([[0., 1., 0.], [0., 1., 0.]])
        hierarchy = build_basin_hierarchy(make_td_source(height, spacing_m=1.))
        topology = build_overflow_topology(hierarchy)
        event = simulate_overflow(topology, np.array([600., 0., 0., 600., 0., 0.]),
                                  parameters=OverflowParameters(timestep_s=300., duration_s=1800.))
        arrays = event["arrays"]
        self.assertAlmostEqual(float(arrays["face_volume_m3"].sum()),
                               float(arrays["face_forward_m3"].sum() + arrays["face_reverse_m3"].sum()))
        self.assertGreaterEqual(float(arrays["face_forward_m3"].sum()), 0.)
        self.assertGreaterEqual(float(arrays["face_reverse_m3"].sum()), 0.)
        self.assertTrue(np.allclose(arrays["face_net_m3"], arrays["face_forward_m3"] - arrays["face_reverse_m3"]))
        self.assertTrue(np.allclose(arrays["basin_net_internal_m3"].sum(axis=1), 0.))

    def test_rejects_non_integer_duration_and_invalid_rain(self):
        with self.assertRaises(ValueError):
            OverflowParameters(timestep_s=7., duration_s=10.)
        height = np.array([[0., 2., 0.]])
        hierarchy = build_basin_hierarchy(make_td_source(height, spacing_m=1.))
        topology = build_overflow_topology(hierarchy)
        with self.assertRaises(ValueError):
            simulate_overflow(topology, np.array([-1.]))

    def test_event_cold_read_is_pinned_and_does_not_recompute(self):
        height = np.array([[0., 2., 0.]])
        hierarchy = build_basin_hierarchy(make_td_source(height, spacing_m=1.))
        topology = build_overflow_topology(hierarchy)
        event = simulate_overflow(topology, np.full(12, 12000.),
                                  parameters=OverflowParameters(timestep_s=300., duration_s=3600.))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "event.json"
            save_overflow_event(event, path)
            loaded = load_overflow_event(path, expected_sha256=file_sha256(path),
                                         expected_identity=event["identity_sha256"], topology=topology)
            self.assertEqual(loaded["identity_sha256"], event["identity_sha256"])
            with self.assertRaises(ValueError):
                load_overflow_event(path, expected_sha256="0" * 64,
                                    expected_identity=event["identity_sha256"], topology=topology)


if __name__ == "__main__":
    unittest.main()
