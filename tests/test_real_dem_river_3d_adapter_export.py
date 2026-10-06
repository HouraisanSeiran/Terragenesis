import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

from terrain_pipeline.artifacts.contracts import array_hash, digest
from terrain_pipeline.real_dem_flat_routing import resolve_dem_flats
from tools import verify_real_dem_river_3d_adapter as exporter


class River3DAdapterExportTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        height = np.arange(32 * 32, dtype=np.float64).reshape(32, 32)
        self.candidate = {"arrays": {"height_m": height, "valid_mask": np.ones(height.shape, bool)},
                          "grid": {"origin_x_m": 400000., "origin_z_m": -3200000.,
                                   "spacing_x_m": 90., "spacing_z_m": 90.,
                                   "crs": "EPSG:32651", "units": "metres"}}
        self.flat = resolve_dem_flats(self.candidate)
        self.candidate_path = self.root / "candidate.npz"
        self.candidate_path.write_bytes(b"proof fixture candidate")
        self.flat_path = self.root / "flat"
        self.flat_path.mkdir()
        self.write_flat()
        self.review = self.root / "review"
        self.rainfall = self.root / "rainfall"
        self.review.mkdir()
        self.rainfall.mkdir()
        for name in ("manifest.json", "static-layers.json", "zero_dry.json", "uniform.json", "pulse.json"):
            (self.review / name).write_text("{}", encoding="ascii")
        for name in ("manifest.json", "report.json", "zero_dry.npz", "uniform.npz", "pulse.npz"):
            (self.rainfall / name).write_bytes(b"proof fixture")
        self.proof = {"inputs": [exporter.source_record(path) for path in
                                 (self.candidate_path, self.flat_path / "manifest.json",
                                  self.flat_path / "report.json", self.flat_path / "network.npz")]}
        for name, value in (("ROOT", self.root), ("DEFAULT_CANDIDATE", self.candidate_path),
                            ("DEFAULT_FLAT", self.flat_path)):
            patcher = patch.object(exporter, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        proof_patch = patch.object(exporter.review_exporter, "verify_package", return_value=self.proof)
        self.proof_mock = proof_patch.start()
        self.addCleanup(proof_patch.stop)
        candidate_patch = patch.object(exporter, "load_dem_candidate", return_value=self.candidate)
        candidate_patch.start()
        self.addCleanup(candidate_patch.stop)
        self.output = self.root / "verification" / "real-dem-river-3d-adapter"

    def write_flat(self):
        arrays = exporter.rainfall_exporter.flat_exporter.result_arrays(self.flat)
        np.savez_compressed(self.flat_path / "network.npz", **arrays)
        (self.flat_path / "report.json").write_bytes(exporter.canonical_bytes(
            {"components": self.flat["components"], "summary": self.flat["summary"]}))
        (self.flat_path / "manifest.json").write_text("{}", encoding="ascii")

    def export(self):
        return exporter.export_package(self.review, self.rainfall, output_root=self.output)

    def rehash(self, directory, arrays=None, record=None):
        if arrays is not None:
            np.savez_compressed(directory / "geometry.npz", **arrays)
        if record is not None:
            record["array_hashes"] = {name: array_hash(arrays[name]) for name in exporter.geometry.ARRAY_NAMES}
            record["metadata_sha256"] = digest(record["metadata"])
            record["content_sha256"] = digest({"array_hashes": record["array_hashes"],
                                                "metadata_sha256": record["metadata_sha256"]})
            (directory / "geometry.json").write_bytes(exporter.canonical_bytes(record))
        manifest = exporter.read_json(directory / "manifest.json")
        if arrays is not None:
            manifest["arrays"] = exporter.rainfall_exporter.flat_exporter.stage_b.array_records(arrays)
        for name in manifest["artifacts"]:
            manifest["artifacts"][name]["sha256"] = exporter.file_sha256(directory / name)
            manifest["artifacts"][name]["bytes"] = (directory / name).stat().st_size
        (directory / "manifest.json").write_bytes(exporter.canonical_bytes(manifest))

    def load_arrays(self, directory):
        with np.load(directory / "geometry.npz", allow_pickle=False) as archive:
            return {name: archive[name].copy() for name in archive.files}

    def test_explicit_missing_gates_rejected(self):
        for args in ([], ["--review-package", str(self.review)], ["--rainfall-package", str(self.rainfall)]):
            with self.subTest(args=args), self.assertRaises(SystemExit) as error:
                exporter.main(args)
            self.assertEqual(error.exception.code, 2)
        self.assertFalse(self.output.exists())

    def test_roundtrip_full_review_gate_and_cold_no_build_or_simulate(self):
        with patch.object(exporter.geometry, "build_river_geometry", wraps=exporter.geometry.build_river_geometry) as build:
            directory, report = self.export()
        self.assertEqual(build.call_count, 2)
        self.assertEqual([call.kwargs["tile_size"] for call in build.call_args_list], [256, 512])
        self.proof_mock.assert_called_once_with(self.review, self.rainfall)
        before = {path.name: path.read_bytes() for path in directory.iterdir()}
        with patch.object(exporter.geometry, "build_river_geometry", side_effect=AssertionError("no cold build")):
            with patch.object(exporter.rainfall_exporter.rainfall, "simulate_dem_rainfall", side_effect=AssertionError("no simulate")):
                self.assertEqual(exporter.verify_package(directory, self.review, self.rainfall), report)
        self.assertFalse(report["publishable"])
        self.assertEqual(before, {path.name: path.read_bytes() for path in directory.iterdir()})
        self.assertEqual(list(self.output.iterdir()), [directory])
        self.assertTrue(all(item["global_nodes_unique"] for item in report["seams"]))

    def test_fake_source_and_missing_fixed_flat_binding_rejected(self):
        original = copy.deepcopy(self.proof)
        self.proof["inputs"][0]["sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "source hash mismatch"):
            self.export()
        self.proof["inputs"] = original["inputs"][:-1]
        with self.assertRaisesRegex(ValueError, "not bound"):
            self.export()

    def test_rehashed_node_face_risk_duplicate_id_and_natural_rejected(self):
        for kind in ("node", "face", "risk", "duplicate", "natural", "parameter"):
            directory, report = self.export()
            arrays = self.load_arrays(directory)
            record = exporter.read_json(directory / "geometry.json")
            self.assertGreater(len(arrays["node_ids"]), 1)
            if kind == "node":
                arrays["node_xyz"][0, 1] += 10.
            elif kind == "face":
                arrays["faces"][0, 0] += 1
            elif kind == "risk":
                arrays["touches_unknown"][0] = not arrays["touches_unknown"][0]
            elif kind == "duplicate":
                arrays["node_ids"][1] = arrays["node_ids"][0]
            elif kind == "parameter":
                record["metadata"]["parameters"]["width_m"] = 40.
            else:
                record["metadata"]["natural_outlet_verified"] = True
            self.rehash(directory, arrays, record)
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                exporter.verify_package(directory, self.review, self.rainfall)

    def test_archive_member_dtype_shape_object_rejected(self):
        for kind in ("extra", "missing", "dtype", "shape", "object"):
            directory, report = self.export()
            arrays = self.load_arrays(directory)
            if kind == "extra":
                arrays["extra"] = np.zeros(1)
            elif kind == "missing":
                arrays.pop("faces")
            elif kind == "dtype":
                arrays["node_ids"] = arrays["node_ids"].astype(np.float64)
            elif kind == "shape":
                arrays["vertices"] = arrays["vertices"].ravel()
            else:
                arrays["node_ids"] = arrays["node_ids"].astype(object)
            self.rehash(directory, arrays)
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                exporter.verify_package(directory, self.review, self.rainfall)

    def test_obj_shared_index_forgery_rejected(self):
        directory, report = self.export()
        mesh = directory / ("mesh.obj" if report["mesh_accepted"] else "diagnostic-mesh.obj")
        with mesh.open("a", encoding="ascii") as stream:
            stream.write("f 1 1 1\n")
        self.rehash(directory)
        with self.assertRaisesRegex(ValueError, "OBJ content"):
            exporter.verify_package(directory, self.review, self.rainfall)

    def test_source_mutation_and_half_write_cleanup(self):
        original = exporter.build

        def mutate(*args):
            result = original(*args)
            self.candidate_path.write_bytes(b"changed")
            return result

        with patch.object(exporter, "build", side_effect=mutate):
            with self.assertRaisesRegex(ValueError, "source changed"):
                self.export()
        self.assertEqual(list(self.output.iterdir()), [])

    def test_partial_write_cleanup(self):
        with patch.object(Path, "write_bytes", side_effect=OSError("failed half write")):
            with self.assertRaises(OSError):
                self.export()
        self.assertEqual(list(self.output.iterdir()), [])

    def test_tile_mismatch_is_not_published(self):
        original = exporter.geometry.build_river_geometry

        def different(*args, **kwargs):
            result = original(*args, **kwargs)
            if kwargs["tile_size"] == 512:
                result["node_xyz"][0, 1] += 1.
            return result

        with patch.object(exporter.geometry, "build_river_geometry", side_effect=different):
            with self.assertRaises(ValueError):
                self.export()
        self.assertFalse(self.output.exists())

    def test_degenerate_mesh_gate_only_publishes_diagnostic_obj(self):
        original = exporter.geometry._banks

        def rejected_banks(*args):
            profile, vertices, faces, bad, fallback = original(*args)
            return profile, vertices, faces, np.array([0], dtype=np.int64), fallback

        with patch.object(exporter.geometry, "_banks", side_effect=rejected_banks):
            directory, report = self.export()
            self.assertFalse(report["mesh_accepted"])
            self.assertFalse(report["publishable"])
            self.assertFalse((directory / "mesh.obj").exists())
            diagnostic = directory / "diagnostic-mesh.obj"
            self.assertIn("DIAGNOSTIC ONLY", diagnostic.read_text(encoding="ascii"))
            self.assertEqual(exporter.verify_package(directory, self.review, self.rainfall), report)

    def test_nonempty_real_tile_seams_exact_content(self):
        height = -np.arange(270 * 4, dtype=np.float64).reshape(270, 4)
        candidate = {"arrays": {"height_m": height, "valid_mask": np.ones(height.shape, bool)},
                     "grid": dict(self.candidate["grid"])}
        flat = resolve_dem_flats(candidate)
        result = exporter.build(candidate, flat)
        report = exporter.topology_report(candidate, result)
        self.assertGreater(report["seams"][0]["cross_tile_edges"], 0)
        self.assertEqual(report["seams"][1]["cross_tile_edges"], 0)
        self.assertEqual(len(result["vertices"]), 2 * len(result["node_ids"]))


if __name__ == "__main__":
    unittest.main()
