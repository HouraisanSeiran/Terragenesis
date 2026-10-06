from pathlib import Path
import unittest
from unittest.mock import patch

import numpy as np

from tests import test_real_dem_flat_routing_export as flat_tests
from tools import verify_real_dem_rainfall_routing as exporter


class RainfallRoutingExportTests(unittest.TestCase):
    def setUp(self):
        fixture = flat_tests.FlatRoutingExportTests("test_atomic_write_failure_and_unsafe_output")
        self.addCleanup(fixture.doCleanups)
        fixture.setUp()
        self.fixture = fixture
        self.root = fixture.root
        root_patch = patch.object(exporter, "ROOT", self.root)
        root_patch.start()
        self.addCleanup(root_patch.stop)
        self.flat_path, unused = fixture.export()
        self.options = {**fixture.options, "flat_path": self.flat_path}
        self.output_root = self.root / "verification" / "real-dem-rainfall-routing"

    def export(self):
        return exporter.export_package(output_root=self.output_root, **self.options)

    def load_arrays(self, directory, name="uniform"):
        with np.load(directory / (name + ".npz"), allow_pickle=False) as archive:
            return {key: archive[key].copy() for key in archive.files}

    def rehash(self, directory, report, name, arrays):
        np.savez_compressed(directory / (name + ".npz"), **arrays)
        (directory / "report.json").write_bytes(exporter.canonical_bytes(report))
        manifest = exporter.read_json(directory / "manifest.json")
        manifest["arrays"][name] = exporter.flat_exporter.stage_b.array_records(arrays)
        for key in ("report.json", name + ".npz"):
            manifest["artifacts"][key]["sha256"] = exporter.file_sha256(directory / key)
            manifest["artifacts"][key]["bytes"] = (directory / key).stat().st_size
        manifest["config"] = report["config"]
        manifest["config_sha256"] = exporter.value_hash(report["config"])
        (directory / "manifest.json").write_bytes(exporter.canonical_bytes(manifest))

    def test_roundtrip_fixed_forcing_and_cold_no_simulation(self):
        with patch.object(exporter.rainfall, "simulate_dem_rainfall", wraps=exporter.rainfall.simulate_dem_rainfall) as simulate:
            with patch.object(exporter.rainfall, "validate_dem_rainfall", wraps=exporter.rainfall.validate_dem_rainfall) as validate:
                directory, report = self.export()
        self.assertEqual(simulate.call_count, 3)
        self.assertEqual(validate.call_count, 3)
        self.assertEqual(set(report["scenarios"]), set(exporter.SCENARIOS))
        for name in exporter.SCENARIOS:
            arrays = self.load_arrays(directory, name)
            self.assertEqual(set(arrays), exporter.MEMBERS)
            self.assertEqual(arrays["local_volume"].shape[0], 24)
        dry = report["scenarios"]["zero_dry"]
        self.assertEqual(dry["summary"]["rain_volume_m3"], 0.)
        self.assertEqual(dry["summary"]["final_channel_storage_m3"], 0.)
        pulse = report["scenarios"]["pulse"]["forcing"]["rain_mm_h"]
        self.assertEqual(pulse[2:4], [40., 40.])
        self.assertEqual(sum(pulse), 80.)
        before = {path.name: path.read_bytes() for path in directory.iterdir()}
        with patch.object(exporter.rainfall, "simulate_dem_rainfall", side_effect=AssertionError("cold simulation forbidden")):
            with patch.object(exporter.rainfall, "validate_dem_rainfall", wraps=exporter.rainfall.validate_dem_rainfall) as validate:
                self.assertEqual(exporter.verify_package(directory, **self.options), report)
        self.assertEqual(validate.call_count, 3)
        self.assertEqual(before, {path.name: path.read_bytes() for path in directory.iterdir()})
        self.assertEqual(list(self.output_root.iterdir()), [directory])

    def test_full_flat_proof_called_and_default_is_fixed(self):
        self.assertEqual(exporter.DEFAULT_FLAT.name, "run-20261001T154605807741Z")
        with patch.object(exporter.flat_exporter, "verify_package", wraps=exporter.flat_exporter.verify_package) as verify:
            directory, report = self.export()
        self.assertEqual(verify.call_count, 1)
        self.assertEqual(verify.call_args.args[0], self.flat_path)
        expected = sorted(record["cell_id"] for record in exporter.read_json(self.flat_path / "report.json")["terminals"]
                          if record["classification"] == "boundary_clip" and not record["component_touches_unknown"])
        self.assertEqual(report["risk"]["engineering_terminal_ids"], expected)
        for record in report["scenarios"].values():
            self.assertEqual(record["metadata"]["engineering_terminal_ids"], expected)
            self.assertFalse(record["metadata"]["natural_outlet_verified"])

    def test_rehashed_fixed_rain_and_initial_parameters_rejected(self):
        from terrain_pipeline.artifacts.contracts import array_hash, digest
        for kind in ("rain", "initial", "dt", "engineering"):
            directory, report = self.export()
            arrays = self.load_arrays(directory)
            record = report["scenarios"]["uniform"]
            if kind == "rain":
                arrays["rain_mm_h"][0] += 1.
                record["metadata"]["rain_sha256"] = array_hash(arrays["rain_mm_h"])
                record["forcing"]["rain_mm_h"][0] += 1.
                report["config"]["scenarios"]["uniform"]["rain_mm_h"][0] += 1.
            elif kind == "initial":
                record["metadata"]["parameters"]["initial_soil_mm"] += 1.
                record["metadata"]["parameter_sha256"] = digest(record["metadata"]["parameters"])
                record["forcing"]["parameters"] = dict(record["metadata"]["parameters"])
                report["config"]["scenarios"]["uniform"]["parameters"] = dict(record["metadata"]["parameters"])
            elif kind == "dt":
                record["metadata"]["dt_s"] = 1800.
            else:
                record["metadata"]["engineering_terminal_ids"] = []
            self.rehash(directory, report, "uniform", arrays)
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                exporter.verify_package(directory, **self.options)

    def test_rehashed_equation_state_volume_and_discharge_rejected(self):
        for key in ("local_volume", "channel_storage", "final_soil_mm", "final_fast_mm", "final_slow_mm",
                    "ledger_engineering_discharge_m3", "ledger_unknown_retained_m3"):
            directory, report = self.export()
            arrays = self.load_arrays(directory)
            arrays[key].flat[-1] += 1.
            if key.startswith("ledger_"):
                report["scenarios"]["uniform"]["ledger"][key[7:]] = arrays[key].tolist()
            self.rehash(directory, report, "uniform", arrays)
            with self.subTest(key=key), self.assertRaises(ValueError):
                exporter.verify_package(directory, **self.options)

    def test_archive_members_dtype_shape_and_object_rejected(self):
        for kind in ("extra", "missing", "dtype", "shape", "object"):
            directory, report = self.export()
            arrays = self.load_arrays(directory)
            if kind == "extra":
                arrays["extra"] = np.zeros(1)
            elif kind == "missing":
                arrays.pop("rain_mm_h")
            elif kind == "dtype":
                arrays["local_volume"] = arrays["local_volume"].astype(np.float32)
            elif kind == "shape":
                arrays["local_volume"] = arrays["local_volume"].ravel()
            else:
                arrays["rain_mm_h"] = arrays["rain_mm_h"].astype(object)
            self.rehash(directory, report, "uniform", arrays)
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                exporter.verify_package(directory, **self.options)

    def test_natural_flag_current_code_and_path_forgery_rejected(self):
        for kind in ("natural", "code", "path"):
            directory, report = self.export()
            if kind == "natural":
                report["risk"]["natural_outlet_verified"] = True
                self.rehash(directory, report, "uniform", self.load_arrays(directory))
            else:
                manifest = exporter.read_json(directory / "manifest.json")
                if kind == "code":
                    manifest["algorithm"]["rainfall_code_sha256"] = "0" * 64
                    manifest["algorithm_sha256"] = exporter.value_hash(manifest["algorithm"])
                else:
                    manifest["artifacts"]["uniform.npz"]["path"] = "../uniform.npz"
                (directory / "manifest.json").write_bytes(exporter.canonical_bytes(manifest))
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                exporter.verify_package(directory, **self.options)

    def test_source_mutation_prevents_publication_and_write_failure(self):
        original = exporter.rainfall.simulate_dem_rainfall

        def mutate(*args, **kwargs):
            result = original(*args, **kwargs)
            self.fixture.fixture.archive.write_bytes(b"changed source")
            return result

        with patch.object(exporter.rainfall, "simulate_dem_rainfall", side_effect=mutate):
            with self.assertRaisesRegex(ValueError, "source changed"):
                self.export()
        self.assertEqual(list(self.output_root.iterdir()), [])

    def test_atomic_write_failure_and_strict_output(self):
        with patch.object(exporter.np, "savez_compressed", side_effect=OSError("failed")):
            with self.assertRaises(OSError):
                self.export()
        self.assertEqual(list(self.output_root.iterdir()), [])
        for output in (self.root / "data", self.root / "verification" / "other", self.flat_path):
            with self.subTest(output=output), self.assertRaises(ValueError):
                exporter.export_package(output_root=output, **self.options)

    def test_budget_rejection_before_simulation(self):
        with patch.object(exporter.rainfall, "MAX_BYTES", 1):
            with patch.object(exporter.rainfall, "simulate_dem_rainfall", side_effect=AssertionError("must preflight")):
                with self.assertRaisesRegex(ValueError, "budget exceeded"):
                    self.export()
        self.assertFalse(self.output_root.exists())


if __name__ == "__main__":
    unittest.main()
