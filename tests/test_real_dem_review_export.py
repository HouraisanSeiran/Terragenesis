from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

from tools import export_real_dem_review as exporter


class RealDemReviewExportTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.rainfall_path = self.root / "rainfall"
        self.rainfall_path.mkdir()
        self.proof_path = self.root / "source.bin"
        self.proof_path.write_bytes(b"fixed synthetic upstream source proof")
        height = np.arange(131., dtype=np.float64).reshape(1, 131)
        height[0, 3] = np.nan
        valid = np.isfinite(height)
        self.candidate = {"arrays": {"height_m": height, "valid_mask": valid},
                          "manifest": {"identity": {"grid": {"origin_x_m": 400000., "origin_z_m": -3200000.,
                              "spacing_x_m": 90., "spacing_z_m": 90., "shape_zx": [1, 131]}}}}
        receiver = np.arange(1, 132, dtype=np.int64).reshape(1, 131)
        receiver[0, -1] = -1
        receiver[0, 3] = -1
        self.raw = {"receiver": receiver, "accumulation_cells": np.arange(1., 132.).reshape(1, 131)}
        self.flat = {**self.raw, "component_id": np.arange(131, dtype=np.int64).reshape(1, 131),
                     "distance_to_exit": np.zeros((1, 131), np.int64)}
        self.flat_report = {"terminals": [{"cell_id": 130, "natural_outlet_verified": False}]}
        ids = np.flatnonzero(valid.ravel())
        steps = exporter.rainfall_exporter.STEPS
        self.results = {}
        self.report = {"scenarios": {}}
        for name in exporter.rainfall_exporter.SCENARIOS:
            local = np.arange(steps * len(ids), dtype=float).reshape(steps, len(ids)) / 1000
            storage = np.vstack((np.zeros(len(ids)), np.cumsum(local, axis=0)))
            ledger = {key: np.zeros(steps) for key in exporter.rainfall_exporter.LEDGER_KEYS}
            ledger["local_runoff_m3"] = local.sum(axis=1)
            result = {"valid_cell_ids": ids, "rain_mm_h": np.zeros(steps), "local_volume": local,
                      "channel_storage": storage, "metadata": {"dt_s": 900., "natural_outlet_verified": False},
                      "summary": {"final_channel_storage_m3": float(storage[-1].sum()), "natural_outlet_verified": False},
                      "ledger": ledger, **{"final_" + field + "_mm": np.zeros(len(ids)) for field in ("soil", "fast", "slow")}}
            self.results[name] = result
            self.report["scenarios"][name] = {"metadata": result["metadata"], "summary": result["summary"],
                                              "ledger": {key: value.tolist() for key, value in ledger.items()}}
            np.savez_compressed(self.rainfall_path / (name + ".npz"), **exporter.rainfall_exporter.saved_arrays(result))
        (self.rainfall_path / "report.json").write_bytes(exporter.canonical_bytes(self.report))
        (self.rainfall_path / "manifest.json").write_bytes(exporter.canonical_bytes({"inputs": {}, "source_files": []}))
        self.inputs = [exporter.source_record(self.proof_path)]
        self.inputs += [exporter.source_record(path) for path in sorted(self.rainfall_path.iterdir())]
        self.output = self.root / "verification/real-dem-review"
        root_patch = patch.object(exporter, "ROOT", self.root)
        root_patch.start()
        self.addCleanup(root_patch.stop)
        self.proof = (self.rainfall_path, self.report, self.candidate, self.flat_report, self.flat, self.raw, self.inputs)

    def export(self):
        with patch.object(exporter, "source_inputs", return_value=self.proof):
            return exporter.export_package(self.rainfall_path, output_root=self.output)

    def verify(self, directory):
        with patch.object(exporter, "source_inputs", return_value=self.proof):
            return exporter.verify_package(directory, self.rainfall_path)

    def rehash(self, directory, name, payload):
        (directory / name).write_bytes(exporter.canonical_bytes(payload))
        manifest = exporter.read_json(directory / "manifest.json")
        manifest["artifacts"][name].update(sha256=exporter.file_sha256(directory / name),
                                           bytes=(directory / name).stat().st_size)
        (directory / "manifest.json").write_bytes(exporter.canonical_bytes(manifest))

    def test_layers_unknown_null_masks_coordinates_and_no_false_natural(self):
        layers = exporter.layers(self.candidate, self.raw, self.flat, self.flat_report)
        self.assertIsNone(layers["height_m"][0][3])
        self.assertTrue(layers["unknown_mask"][0][3])
        self.assertFalse(layers["valid_mask"][0][3])
        self.assertEqual(layers["grid"], self.candidate["manifest"]["identity"]["grid"])
        self.assertEqual(layers["terminals"], self.flat_report["terminals"])
        self.assertFalse(layers["natural_outlet_verified"])
        self.assertFalse(layers["ocean_outlet_certified"])
        exporter.canonical_bytes(layers)

    def test_dynamic_states_intervals_selected_omitted_conservation(self):
        result = self.results["uniform"]
        review = exporter.dynamic_review(result, self.flat)
        steps = exporter.rainfall_exporter.STEPS
        self.assertEqual(len(review["time_state_s"]), steps + 1)
        self.assertEqual(len(review["time_interval_start_s"]), steps)
        self.assertEqual(review["time_state_s"][-1], steps * 900.)
        self.assertEqual(review["selected_global_cell_ids"], list(range(99, 131)))
        selected_storage = np.asarray(review["selected_storage_m3"])
        np.testing.assert_allclose(selected_storage.sum(axis=1) + review["omitted_storage_m3"], review["whole_domain_storage_m3"])
        selected_local = np.asarray(review["selected_local_runoff_q_m3_s"]) * 900.
        np.testing.assert_allclose(selected_local.sum(axis=1) + review["omitted_local_runoff_m3"], result["local_volume"].sum(axis=1))
        self.assertEqual(review["selection"]["selected_cells"] + review["selection"]["omitted_valid_cells"], len(result["valid_cell_ids"]))

    def test_export_and_cold_do_not_simulate_and_are_readonly(self):
        with patch.object(exporter.rainfall_exporter.rainfall, "simulate_dem_rainfall", side_effect=AssertionError("no simulation")):
            directory = self.export()
            before = {path.name: path.read_bytes() for path in directory.iterdir()}
            manifest = self.verify(directory)
        self.assertEqual(before, {path.name: path.read_bytes() for path in directory.iterdir()})
        self.assertEqual(list(self.output.iterdir()), [directory])
        self.assertTrue(manifest["readonly"])
        self.assertTrue(manifest["no_inference_no_routing_no_dynamic_advancement"])
        self.assertFalse(manifest["water_surface_available"])

    def test_source_inputs_calls_full_proof_and_reads_saved_networks(self):
        flat_path = self.root / "flat"
        raw_path = self.root / "raw"
        flat_path.mkdir()
        raw_path.mkdir()
        (flat_path / "report.json").write_bytes(exporter.canonical_bytes(self.flat_report))
        np.savez_compressed(flat_path / "network.npz", **self.flat)
        np.savez_compressed(raw_path / "network.npz", **self.raw)
        with patch.object(exporter.rainfall_exporter, "verify_package", return_value=self.report) as verify, \
                patch.object(exporter, "load_dem_candidate", return_value=self.candidate) as load, \
                patch.object(exporter.rainfall_exporter, "DEFAULT_FLAT", flat_path), \
                patch.object(exporter.rainfall_exporter, "DEFAULT_STAGE_B", raw_path), \
                patch.object(exporter.rainfall_exporter.rainfall, "simulate_dem_rainfall", side_effect=AssertionError("no simulation")):
            proof = exporter.source_inputs(self.rainfall_path)
        verify.assert_called_once_with(self.rainfall_path.resolve())
        load.assert_called_once_with(exporter.DEFAULT_CANDIDATE, verify_source=True)
        np.testing.assert_array_equal(proof[4]["receiver"], self.flat["receiver"])
        paths = {item["path"] for item in proof[-1]}
        self.assertIn(str(Path(exporter.__file__).resolve()), paths)
        for name in ("manifest.json", "report.json", "uniform.npz", "pulse.npz", "zero_dry.npz"):
            self.assertIn(str((self.rainfall_path / name).resolve()), paths)

    def test_failed_upstream_proof_prevents_writes(self):
        with patch.object(exporter.rainfall_exporter, "verify_package", side_effect=ValueError("invalid upstream proof")):
            with self.assertRaisesRegex(ValueError, "upstream proof"):
                exporter.export_package(self.rainfall_path, output_root=self.output)
        self.assertFalse(self.output.exists())

    def test_rehashed_dynamic_statistics_time_and_natural_forgery_rejected(self):
        for kind in ("omitted", "storage", "time", "count", "natural", "summary"):
            directory = self.export()
            payload = exporter.read_json(directory / "uniform.json")
            if kind == "omitted":
                payload["omitted_storage_m3"][-1] += 1
            elif kind == "storage":
                payload["selected_storage_m3"][-1][0] += 1
            elif kind == "time":
                payload["time_state_s"] = payload["time_state_s"][:-1]
            elif kind == "count":
                payload["selection"]["omitted_valid_cells"] += 1
            elif kind == "natural":
                payload["natural_outlet_verified"] = True
            else:
                payload["summary"]["final_channel_storage_m3"] += 1
            self.rehash(directory, "uniform.json", payload)
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                self.verify(directory)

    def test_rehashed_static_null_receiver_and_masks_forgery_rejected(self):
        for field in ("height_m", "valid_mask", "raw_receiver_global_id"):
            directory = self.export()
            payload = exporter.read_json(directory / "static-layers.json")
            payload[field][0][3] = 0
            self.rehash(directory, "static-layers.json", payload)
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.verify(directory)

    def test_manifest_input_code_hash_path_and_false_claims_rejected(self):
        for kind in ("input", "code", "path", "natural"):
            directory = self.export()
            manifest = exporter.read_json(directory / "manifest.json")
            if kind == "input":
                manifest["inputs"][0]["sha256"] = "0" * 64
            elif kind == "code":
                manifest["algorithm"]["exporter_sha256"] = "0" * 64
            elif kind == "path":
                manifest["artifacts"]["uniform.json"]["path"] = "../uniform.json"
            else:
                manifest["ocean_outlet_certified"] = True
            (directory / "manifest.json").write_bytes(exporter.canonical_bytes(manifest))
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                self.verify(directory)

    def test_extra_members_duplicate_json_and_byte_budget_rejected(self):
        directory = self.export()
        (directory / "extra.json").write_text("{}", encoding="utf8")
        with self.assertRaises(ValueError):
            self.verify(directory)
        (directory / "extra.json").unlink()
        (directory / "manifest.json").write_text('{"schema":1,"schema":2}', encoding="utf8")
        with self.assertRaises(ValueError):
            self.verify(directory)
        with patch.object(exporter, "MAX_JSON_BYTES", 10):
            with self.assertRaises(ValueError):
                self.export()

    def test_atomic_write_and_source_mutation_failure_leave_no_partial_bundle(self):
        with patch.object(exporter, "write_json", side_effect=OSError("write failure")):
            with self.assertRaises(OSError):
                self.export()
        self.assertEqual(list(self.output.iterdir()), [])
        original = exporter.write_json

        def mutate(path, payload):
            original(path, payload)
            self.proof_path.write_bytes(b"source changed")

        with patch.object(exporter, "write_json", side_effect=mutate):
            with self.assertRaisesRegex(ValueError, "source changed"):
                self.export()
        self.assertEqual(list(self.output.iterdir()), [])

    def test_cold_rejects_changed_source_and_input_archives(self):
        for source in (self.proof_path, self.rainfall_path / "pulse.npz"):
            before = source.read_bytes()
            directory = self.export()
            source.write_bytes(before + b"changed")
            with self.subTest(source=source), self.assertRaises(ValueError):
                self.verify(directory)
            source.write_bytes(before)

    def test_output_path_and_input_overlap_rejected(self):
        for output in (self.root, self.root / "verification", self.root / "verification/other"):
            with self.subTest(output=output), self.assertRaises(ValueError):
                exporter.export_package(self.rainfall_path, output_root=output)
        with self.assertRaises(ValueError):
            exporter.check_output(self.output, [{"path": str(self.output / "source.json")}])


if __name__ == "__main__":
    unittest.main()
