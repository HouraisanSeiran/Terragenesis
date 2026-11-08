from pathlib import Path
import unittest
from unittest.mock import patch

import numpy as np

from terrain_pipeline.drainage import resolve_dem_flats as resolve_dem_flats
from terrain_pipeline.drainage import validate_flat_routing as validate_flat_routing
from tests import test_real_dem_tiled_network_export as tiled_tests
from tools import verify_real_dem_flat_routing as exporter


class FlatRoutingExportTests(unittest.TestCase):
    def setUp(self):
        fixture = tiled_tests.TiledNetworkExportTests("test_write_failure_atomic_cleanup")
        self.addCleanup(fixture.doCleanups)
        fixture.setUp()
        self.fixture = fixture
        self.root = fixture.root
        root_patch = patch.object(exporter, "ROOT", self.root)
        root_patch.start()
        self.addCleanup(root_patch.stop)
        self.stage_b, unused = fixture.export()
        self.options = {**fixture.options, "stage_b_path": self.stage_b}
        self.output_root = self.root / "verification" / "flat"

    def export(self):
        return exporter.export_package(output_root=self.output_root, **self.options)

    def rehash(self, directory, report=None, arrays=None):
        manifest = exporter.read_json(directory / "manifest.json")
        if report is not None:
            (directory / "report.json").write_bytes(exporter.canonical_bytes(report))
            manifest["deterministic_report_sha256"] = exporter.value_hash(exporter.deterministic_report(report))
        if arrays is not None:
            np.savez_compressed(directory / "network.npz", **arrays)
            manifest["arrays"] = exporter.stage_b.array_records(arrays)
        for name in ("report.json", "network.npz"):
            manifest["artifacts"][name]["sha256"] = exporter.file_sha256(directory / name)
            manifest["artifacts"][name]["bytes"] = (directory / name).stat().st_size
        (directory / "manifest.json").write_bytes(exporter.canonical_bytes(manifest))

    def load_arrays(self, directory):
        with np.load(directory / "network.npz", allow_pickle=False) as archive:
            return {name: archive[name].copy() for name in exporter.ARRAY_NAMES}

    def test_roundtrip_full_b_proof_repeated_read_only_replay(self):
        with patch.object(exporter.stage_b, "verify_package", wraps=exporter.stage_b.verify_package) as verify:
            directory, report = self.export()
        self.assertEqual(verify.call_count, 1)
        self.assertEqual(verify.call_args.args[0], self.stage_b)
        self.assertEqual(len(report["comparisons"]), 2)
        self.assertEqual([(item["tile_size"], item["tile_order"]) for item in report["comparisons"]],
                         [(256, "row_major"), (512, "reversed")])
        before = {path.name: path.read_bytes() for path in directory.iterdir()}
        for unused in range(2):
            self.assertEqual(exporter.verify_package(directory, **self.options), report)
        self.assertEqual(before, {path.name: path.read_bytes() for path in directory.iterdir()})
        self.assertEqual(list(self.output_root.iterdir()), [directory])
        self.assertEqual(report["risk"]["contributing_cells_sum"], report["summary"]["valid_cells"])
        manifest = exporter.read_json(directory / "manifest.json")
        self.assertIn("stage_b_network.npz", manifest["inputs"])

    def test_rehashed_component_risk_and_natural_flag_rejected(self):
        for kind in ("risk", "natural", "terminal_count"):
            directory, report = self.export()
            if kind == "risk":
                report["components"][0]["touches_unknown"] = not report["components"][0]["touches_unknown"]
            elif kind == "natural":
                report["components"][0]["natural_outlet_verified"] = True
            else:
                report["risk"]["classification_counts"]["internal_retention"] += 1
            self.rehash(directory, report=report)
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                exporter.verify_package(directory, **self.options)

    def test_rehashed_unknown_barrier_reverse_rank_and_uphill_rejected(self):
        for kind in ("unknown", "rank", "uphill"):
            directory, report = self.export()
            arrays = self.load_arrays(directory)
            candidate = exporter.stage_b.load_dem_candidate(self.fixture.candidate_path, verify_source=False)
            valid = candidate["arrays"]["valid_mask"].ravel()
            if kind == "unknown":
                arrays["unknown_adjacent_terminal"].ravel()[np.flatnonzero(valid)[0]] = True
            elif kind == "rank":
                arrays["distance_to_exit"].ravel()[np.flatnonzero(valid)[0]] += 100
            else:
                source_ids = np.flatnonzero(arrays["receiver"].ravel() >= 0)
                source = source_ids[0]
                target = arrays["receiver"].ravel()[source]
                arrays["receiver"].ravel()[target] = source
            self.rehash(directory, arrays=arrays)
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                exporter.verify_package(directory, **self.options)

    def test_rehashed_b_source_package_forgery_rejected(self):
        directory, report = self.export()
        b_report = exporter.read_json(self.stage_b / "report.json")
        b_report["comparisons"][0]["cross_tile_edges"] += 1
        (self.stage_b / "report.json").write_bytes(exporter.canonical_bytes(b_report))
        manifest = self.fixture.rehash_artifact(self.stage_b, "report.json")
        manifest["deterministic_report_sha256"] = exporter.value_hash(exporter.stage_b.deterministic_report(b_report))
        (self.stage_b / "manifest.json").write_bytes(exporter.canonical_bytes(manifest))
        with self.assertRaisesRegex(ValueError, "statistics/reference replay"):
            exporter.verify_package(directory, **self.options)

    def test_members_dtype_shape_object_rejected(self):
        for kind in ("extra", "missing", "dtype", "shape", "object"):
            directory, report = self.export()
            arrays = self.load_arrays(directory)
            if kind == "extra":
                arrays["extra"] = np.zeros(1)
            elif kind == "missing":
                arrays.pop("component_id")
            elif kind == "dtype":
                arrays["component_id"] = arrays["component_id"].astype(np.int32)
            elif kind == "shape":
                arrays["distance_to_exit"] = arrays["distance_to_exit"].ravel()
            else:
                arrays["distance_to_exit"] = arrays["distance_to_exit"].astype(object)
            self.rehash(directory, arrays=arrays)
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                exporter.verify_package(directory, **self.options)

    def test_source_mutation_prevents_publication(self):
        original = exporter.compute

        def mutate(*args):
            result = original(*args)
            self.fixture.archive.write_bytes(b"mutated source")
            return result

        with patch.object(exporter, "compute", side_effect=mutate):
            with self.assertRaisesRegex(ValueError, "source changed"):
                self.export()
        self.assertEqual(list(self.output_root.iterdir()), [])

    def test_atomic_write_failure_and_unsafe_output(self):
        with patch.object(exporter.np, "savez_compressed", side_effect=OSError("simulated failure")):
            with self.assertRaises(OSError):
                self.export()
        self.assertEqual(list(self.output_root.iterdir()), [])
        for output in (self.root / "data", self.stage_b, self.root / "verification"):
            with self.subTest(output=output), self.assertRaises(ValueError):
                exporter.export_package(output_root=output, **self.options)

    def test_component_risks_include_members_remote_from_root(self):
        height = np.full((7, 7), 20., dtype=np.float64)
        height[2:5, 2:5] = 10.
        height[4, 5] = np.nan
        valid = np.isfinite(height)
        candidate = {"arrays": {"height_m": height, "valid_mask": valid, "unknown_mask": ~valid}}
        result = resolve_dem_flats(candidate)
        validate_flat_routing(candidate, result)
        root = 2 * 7 + 2
        self.assertFalse(result["network"].unknown_adjacent_terminal.ravel()[root])
        risk = exporter.terminal_risks(candidate, result)
        record = next(item for item in risk["terminals"] if item["cell_id"] == root)
        self.assertEqual(record["classification"], "unknown_adjacent")
        self.assertTrue(record["component_touches_unknown"])
        self.assertFalse(record["natural_outlet_verified"])
        height[4, 5] = 20.
        height[2:5, 2:7] = 10.
        candidate["arrays"]["valid_mask"] = np.isfinite(height)
        candidate["arrays"]["unknown_mask"] = ~np.isfinite(height)
        result = resolve_dem_flats(candidate)
        self.assertFalse(result["network"].boundary_outlet.ravel()[root])
        record = next(item for item in exporter.terminal_risks(candidate, result)["terminals"] if item["cell_id"] == root)
        self.assertEqual(record["classification"], "boundary_clip")

    def test_rehashed_unknown_cell_component_barrier_semantics(self):
        height = np.ones((7, 7), dtype=np.float64)
        height[4, 5] = np.nan
        valid = np.isfinite(height)
        candidate = {"arrays": {"height_m": height, "valid_mask": valid, "unknown_mask": ~valid}}
        report, arrays, algorithm = exporter.compute(candidate)
        expected = {name: array.copy() for name, array in arrays.items()}
        arrays["component_id"][4, 5] = 0
        path = self.root / "unknown-forged.npz"
        np.savez_compressed(path, **arrays)
        result = exporter.read_result(path, expected, report)
        with self.assertRaisesRegex(ValueError, "unknown/range/component"):
            validate_flat_routing(candidate, result)

    def test_current_code_hash_and_input_path_forgery_rejected(self):
        for kind in ("code", "input"):
            directory, report = self.export()
            manifest = exporter.read_json(directory / "manifest.json")
            if kind == "code":
                manifest["algorithm"]["flat_code_sha256"] = "0" * 64
                manifest["algorithm_sha256"] = exporter.value_hash(manifest["algorithm"])
            else:
                manifest["inputs"]["stage_b_network.npz"]["path"] = str(self.root / "fake.npz")
            (directory / "manifest.json").write_bytes(exporter.canonical_bytes(manifest))
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                exporter.verify_package(directory, **self.options)


if __name__ == "__main__":
    unittest.main()
