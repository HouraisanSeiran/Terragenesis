import hashlib
import shutil
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

import numpy as np
import rasterio
from rasterio.transform import from_origin

from terrain_pipeline.dem_domain import prepare_dem_candidate, save_dem_candidate
from terrain_pipeline.real_dem_surface_network import build_real_dem_network
from tools import verify_real_dem_tiled_network as exporter
from tools.verify_real_dem_outlet_classification import package_manifest


class TiledNetworkExportTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        root_patch = patch.object(exporter, "ROOT", self.root)
        root_patch.start()
        self.addCleanup(root_patch.stop)
        self.source = self.root / "source.tif"
        rows, cols = np.indices((160, 160))
        heights = (rows * 2 + cols).astype(np.float32)
        heights[45:48, 50:53] = -32768.
        with rasterio.open(self.source, "w", driver="GTiff", width=160, height=160,
                           count=1, dtype="float32", crs="EPSG:4326",
                           transform=from_origin(121.35, 29.47, .001, .001),
                           nodata=-32768.) as output:
            output.write(heights, 1)
        candidate = prepare_dem_candidate(
            self.source, (121.40, 29.40, 121.42, 29.42), target_crs="EPSG:32651",
            spacing_m=90., halo_m=180., sea_level_m=0., sea_datum="unknown numeric zero",
            source_declaration="synthetic test elevation assumed metres; local research only")
        self.candidate_path = self.root / "candidate.npz"
        save_dem_candidate(candidate, self.candidate_path)
        self.archive = self.root / "HydroRIVERS_v10_as_shp.zip"
        self.archive.write_bytes(b"synthetic archive")
        record = exporter.source_record(self.archive)
        self.audit_path = self.root / "audit.json"
        self.audit_path.write_bytes(exporter.canonical_bytes({"sources": [
            {"path": record["path"], "bytes": record["bytes"],
             "sha256_before": record["sha256"], "sha256_after": record["sha256"],
             "unchanged": True}]}))
        self.vectors_path = self.root / "vectors.json"
        self.vectors_path.write_bytes(exporter.canonical_bytes({"source_archive_sha256": record["sha256"]}))
        network = build_real_dem_network(candidate["arrays"]["height_m"], candidate["arrays"]["valid_mask"])
        valid = candidate["arrays"]["valid_mask"]
        records = []
        counts = dict.fromkeys(("unknown_adjacent", "boundary_clip", "internal_sink"), 0)
        for cell_id in np.flatnonzero(valid.ravel() & (network.receiver.ravel() < 0)):
            unknown = bool(network.unknown_adjacent_terminal.ravel()[cell_id])
            boundary = bool(network.boundary_outlet.ravel()[cell_id])
            primary = "unknown_adjacent" if unknown else "boundary_clip" if boundary else "internal_sink"
            counts[primary] += 1
            records.append({"cell_id": int(cell_id), "row_col": list(divmod(int(cell_id), valid.shape[1])),
                            "classification": primary, "is_unknown_adjacent": unknown,
                            "is_boundary_clip": boundary, "natural_outlet_verified": False,
                            "contributing_cells": int(network.accumulation_cells.ravel()[cell_id])})
        self.classification = {"outlets": records, "summary": {"classification_counts": counts,
                               "terminal_cells": len(records), "contributing_cells": int(valid.sum())}}
        self.stage_a = self.root / "verification" / "stage-a" / "run-frozen"
        self.stage_a.mkdir(parents=True)
        inputs = {name: exporter.source_record(path) for name, path in
                  (("candidate", self.candidate_path), ("vectors", self.vectors_path), ("audit", self.audit_path))}
        self.sources = [record, exporter.source_record(self.source)]
        self.products = {"classification.json": self.classification,
                         "terminal-layer.geojson": {"type": "FeatureCollection", "features": []},
                         "evidence-levels.json": {"natural_outlet_verified": False}}
        self.stage_a_manifest = package_manifest(self.products, {"export": "frozen-fixture"},
                                                {"match_distance_m": 180.}, inputs, self.sources)
        self.write_stage_a()
        self.output_root = self.root / "verification" / "tiled"
        self.options = {"candidate_path": self.candidate_path, "stage_a_path": self.stage_a,
                        "vectors_path": self.vectors_path, "audit_path": self.audit_path}
        self.real_stage_a_verify = exporter.stage_a_exporter.verify_package
        verifier_patch = patch.object(exporter.stage_a_exporter, "verify_package",
                                      side_effect=lambda *args, **kwargs: self.classification)
        self.stage_a_verify_mock = verifier_patch.start()
        self.addCleanup(verifier_patch.stop)

    def write_stage_a(self):
        for name, value in self.products.items():
            (self.stage_a / name).write_bytes(exporter.canonical_bytes(value))
        (self.stage_a / "manifest.json").write_bytes(exporter.canonical_bytes(self.stage_a_manifest))

    def export(self):
        return exporter.export_package(output_root=self.output_root, **self.options)

    def rehash_artifact(self, directory, name):
        manifest = exporter.read_json(directory / "manifest.json")
        manifest["artifacts"][name]["sha256"] = exporter.file_sha256(directory / name)
        manifest["artifacts"][name]["bytes"] = (directory / name).stat().st_size
        (directory / "manifest.json").write_bytes(exporter.canonical_bytes(manifest))
        return manifest

    def test_roundtrip_repeated_cold_verify_no_files_created(self):
        with patch.object(exporter, "load_dem_candidate", wraps=exporter.load_dem_candidate) as load:
            directory, report = self.export()
        self.assertEqual(load.call_count, 1)
        self.assertTrue(load.call_args.kwargs["verify_source"])
        self.assertEqual(self.stage_a_verify_mock.call_count, 1)
        self.assertEqual(self.stage_a_verify_mock.call_args.kwargs["match_distance_m"], 180.0)
        self.assertEqual(len(report["comparisons"]), 6)
        self.assertTrue(all(item["exact_reference_equal"] for item in report["comparisons"]))
        before = {path.name: path.read_bytes() for path in directory.iterdir()}
        for unused in range(2):
            self.assertEqual(exporter.verify_package(directory, **self.options), report)
        self.assertEqual(before, {path.name: path.read_bytes() for path in directory.iterdir()})
        self.assertEqual(list(self.output_root.iterdir()), [directory])
        second, second_report = self.export()
        self.assertNotEqual(second, directory)
        self.assertEqual(exporter.deterministic_report(report), exporter.deterministic_report(second_report))

    def test_rehashed_false_stats_rejected(self):
        directory, report = self.export()
        report["comparisons"][0]["cross_tile_edges"] += 1
        (directory / "report.json").write_bytes(exporter.canonical_bytes(report))
        manifest = self.rehash_artifact(directory, "report.json")
        manifest["deterministic_report_sha256"] = exporter.value_hash(exporter.deterministic_report(report))
        (directory / "manifest.json").write_bytes(exporter.canonical_bytes(manifest))
        with self.assertRaisesRegex(ValueError, "statistics/reference replay"):
            exporter.verify_package(directory, **self.options)

    def test_rehashed_network_mutation_rejected(self):
        directory, report = self.export()
        with np.load(directory / "network.npz", allow_pickle=False) as archive:
            arrays = {name: archive[name].copy() for name in exporter.ARRAY_NAMES}
        arrays["accumulation_cells"].flat[0] += 1
        np.savez_compressed(directory / "network.npz", **arrays)
        manifest = self.rehash_artifact(directory, "network.npz")
        manifest["arrays"] = exporter.array_records(arrays)
        (directory / "manifest.json").write_bytes(exporter.canonical_bytes(manifest))
        with self.assertRaisesRegex(ValueError, "reference mismatch"):
            exporter.verify_package(directory, **self.options)

    def test_archive_members_dtype_shape_and_object_rejected(self):
        for mutation in ("extra", "missing", "dtype", "shape", "object", "duplicate"):
            with self.subTest(mutation=mutation):
                directory, report = self.export()
                with np.load(directory / "network.npz", allow_pickle=False) as archive:
                    arrays = {name: archive[name].copy() for name in exporter.ARRAY_NAMES}
                if mutation == "extra":
                    arrays["extra"] = np.zeros(1)
                elif mutation == "missing":
                    arrays.pop("order")
                elif mutation == "dtype":
                    arrays["receiver"] = arrays["receiver"].astype(np.float64)
                elif mutation == "shape":
                    arrays["receiver"] = arrays["receiver"].ravel()
                elif mutation == "object":
                    arrays["order"] = arrays["order"].astype(object)
                np.savez_compressed(directory / "network.npz", **arrays)
                if mutation == "duplicate":
                    with zipfile.ZipFile(directory / "network.npz", "a") as archive:
                        archive.writestr("order.npy", b"duplicate")
                self.rehash_artifact(directory, "network.npz")
                with self.assertRaises(ValueError):
                    exporter.verify_package(directory, **self.options)

    def test_stage_a_cell_classification_and_contribution_rejected(self):
        for key, value in (("cell_id", -1), ("classification", "ocean"), ("contributing_cells", 999999)):
            original = self.classification["outlets"][0][key]
            self.classification["outlets"][0][key] = value
            payload = exporter.canonical_bytes(self.classification)
            self.stage_a_manifest["artifacts"]["classification.json"]["sha256"] = hashlib.sha256(payload).hexdigest()
            self.stage_a_manifest["artifacts"]["classification.json"]["bytes"] = len(payload)
            self.write_stage_a()
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.export()
            self.classification["outlets"][0][key] = original
        self.assertFalse(self.output_root.exists())

    def test_source_changed_before_or_during_export_rejected(self):
        original = exporter.compute

        def mutate_source(*args):
            result = original(*args)
            self.archive.write_bytes(b"changed during compute")
            return result

        with patch.object(exporter, "compute", side_effect=mutate_source):
            with self.assertRaisesRegex(ValueError, "source changed"):
                self.export()
        self.assertEqual(list(self.output_root.iterdir()), [])
        with self.assertRaisesRegex(ValueError, "audit source mismatch"):
            self.export()

    def test_illegal_output_and_artifact_path_rejected(self):
        for output in (self.root / "data", self.root / "verification", self.stage_a):
            with self.subTest(output=output), self.assertRaises(ValueError):
                exporter.export_package(output_root=output, **self.options)
        directory, report = self.export()
        manifest = exporter.read_json(directory / "manifest.json")
        manifest["artifacts"]["network.npz"]["path"] = "../network.npz"
        (directory / "manifest.json").write_bytes(exporter.canonical_bytes(manifest))
        with self.assertRaises(ValueError):
            exporter.verify_package(directory, **self.options)

    def test_write_failure_atomic_cleanup(self):
        with patch.object(exporter.np, "savez_compressed", side_effect=OSError("write failed")):
            with self.assertRaises(OSError):
                self.export()
        self.assertEqual(list(self.output_root.iterdir()), [])

    def test_tile_edge_counts_change_without_receiver_change(self):
        height = np.arange(24 * 19, dtype=np.float64).reshape(24, 19)
        network = build_real_dem_network(height, np.ones(height.shape, dtype=bool))
        first = exporter.tile_statistics(network, 4)
        second = exporter.tile_statistics(network, 8)
        self.assertGreater(first["cross_tile_edges"], second["cross_tile_edges"])
        self.assertEqual(first["partial_tiles"], 6)
        self.assertEqual(second["partial_tiles"], 3)

    def test_real_stage_a_rehashed_distance_and_geojson_forgery_rejected(self):
        for name in ("classification.json", "terminal-layer.geojson"):
            directory = self.root / name.replace(".", "-")
            shutil.copytree(exporter.DEFAULT_STAGE_A, directory)
            value = exporter.read_json(directory / name)
            if name == "classification.json":
                nearest = value["outlets"][0]["nearest_hydrovector"]
                numeric_keys = [key for key, item in nearest.items()
                                if isinstance(item, (int, float)) and not isinstance(item, bool)
                                and "distance" in key]
                self.assertTrue(numeric_keys)
                nearest[numeric_keys[0]] += 123.0
            else:
                value["features"][0]["geometry"]["coordinates"][0] += .01
            payload = exporter.canonical_bytes(value)
            (directory / name).write_bytes(payload)
            manifest = exporter.read_json(directory / "manifest.json")
            manifest["artifacts"][name]["sha256"] = hashlib.sha256(payload).hexdigest()
            manifest["artifacts"][name]["bytes"] = len(payload)
            (directory / "manifest.json").write_bytes(exporter.canonical_bytes(manifest))
            with patch.object(exporter.stage_a_exporter, "verify_package", self.real_stage_a_verify):
                with self.subTest(name=name), self.assertRaises(ValueError):
                    exporter.load_inputs(exporter.DEFAULT_CANDIDATE, directory,
                                         exporter.DEFAULT_VECTORS, exporter.DEFAULT_AUDIT)


if __name__ == "__main__":
    unittest.main()
