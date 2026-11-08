import json
import tempfile
import unittest
from pathlib import Path

import numpy as np

from terrain_pipeline.common_infra import file_sha256
from terrain_pipeline.surface_rivers.metric_td_generated_source import load_generated_td_source, load_generated_td_sources


class GeneratedTDSourceTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.height = np.full((513, 513), np.float32(123.4567))
        config = {"meters_per_height_block": 1., "conditioning_mode": "geographic_v5"}
        self.job = {"seed": 17, "domains": [], "generation_identity": "a" * 64,
                    "condition_sha256": "b" * 64, "generation_config": config}
        self.samples = []
        for index in range(6):
            origin = [-1024 + index * 1024, -2048]
            metadata = {"backend": "TerrainDiffusion/WorldPipeline", "native_resolution_m": 30,
                        "seed": "17", "native_origin": origin, "identity": "a" * 64}
            path = self.root / (str(index) + ".npz")
            np.savez_compressed(path, elevation=self.height, climate=np.zeros((4, 513, 513), np.float32),
                                metadata=np.array(json.dumps(metadata)), generation_config=np.array(json.dumps(config)))
            self.job["domains"].append({"origin_xz": origin})
            self.samples.append({"seed": 17, "native_origin": origin, "raw_npz": path.name,
                "raw_sha256": file_sha256(path), "generation_identity": "a" * 64, "condition_sha256": "b" * 64})
        self.plan_path = self.root / "plan.json"
        self.plan_path.write_text(json.dumps({"jobs": [self.job]}), encoding="utf-8")
        self.report_path = self.root / "report.json"
        self.report = {"schema": "TD-noise-climate-generation-v1", "status": "completed",
                       "plan_path": str(self.plan_path), "plan_sha256": file_sha256(self.plan_path), "samples": self.samples}
        self._save_report()

    def _save_report(self):
        self.report_path.write_text(json.dumps(self.report), encoding="utf-8")

    def test_full_precision_coordinates_unknown_edges_and_manifest_order(self):
        sources = load_generated_td_sources(self.report_path, expected_report_sha256=file_sha256(self.report_path))
        self.assertEqual([source["metadata"]["source_metadata"]["sample_index"] for source in sources], list(range(6)))
        source = sources[0]
        terrain, boundary = source["terrain"], source["boundary"]
        np.testing.assert_array_equal(terrain.elevation_m, self.height.astype(np.float64))
        self.assertEqual(terrain.world_xz(514), (-30720. + 30., -61440. + 30.))
        self.assertEqual(terrain.vertical_datum, "unknown_local_relative")
        self.assertIsNone(terrain.crs)
        self.assertTrue((boundary.kind[0] == "unknown_boundary").all())
        self.assertTrue((boundary.kind[:, -1] == "unknown_boundary").all())
        self.assertEqual(boundary.kind[1, 1], "interior")
        self.assertFalse(boundary.allow_inflow.any())
        self.assertFalse(terrain.elevation_m.flags.writeable)
        self.assertEqual(source["metadata"]["node_span_m_xz"], [15360., 15360.])
        self.assertEqual(source["metadata"]["grid_extent_m_xz"], [15390., 15390.])

    def test_reordered_or_subset_manifest_and_byte_tampering_rejected(self):
        self.report["samples"] = self.samples[::-1]
        self._save_report()
        with self.assertRaisesRegex(ValueError, "frozen plan order"):
            load_generated_td_source(self.report_path, 0)
        self.report["samples"] = self.samples[:-1]
        self._save_report()
        with self.assertRaisesRegex(ValueError, "six samples"):
            load_generated_td_sources(self.report_path)
        self.report["samples"] = self.samples
        self._save_report()
        with (self.root / "0.npz").open("ab") as stream:
            stream.write(b"tampered")
        with self.assertRaisesRegex(ValueError, "source SHA256"):
            load_generated_td_source(self.report_path, 0)

    def test_config_and_datum_contract(self):
        path = self.root / "0.npz"
        with np.load(path, allow_pickle=False) as archive:
            arrays = {key: archive[key] for key in archive.files}
        metadata = json.loads(str(arrays["metadata"].item()))
        metadata["vertical_datum"] = "declared_test_datum"
        arrays["metadata"] = np.array(json.dumps(metadata))
        np.savez_compressed(path, **arrays)
        self.samples[0]["raw_sha256"] = file_sha256(path)
        self._save_report()
        self.assertEqual(load_generated_td_source(self.report_path, 0)["terrain"].vertical_datum, "declared_test_datum")
        arrays["generation_config"] = np.array(json.dumps({"different": True}))
        np.savez_compressed(path, **arrays)
        self.samples[0]["raw_sha256"] = file_sha256(path)
        self._save_report()
        with self.assertRaisesRegex(ValueError, "configuration differs"):
            load_generated_td_source(self.report_path, 0)


if __name__ == "__main__":
    unittest.main()
