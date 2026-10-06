import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch
import json
import hashlib

import numpy as np

from diffusion.config import GenerationConfig
from diffusion.geography_v3 import make_geographic_map_factory as v3_factory
from diffusion.geography_v4 import make_geographic_map_factory as v4_factory
from tools.prepare_height_budget_v4 import (prepare_batch_with_retry, publish_batch,
                                            height_result)


class GeographicV4Tests(unittest.TestCase):
    def test_old_identity_and_record_unchanged(self):
        config = GenerationConfig.for_profile("geographic_v3")
        self.assertEqual(config.identity()[0],
                         "59d7386681f42fc43bdd8bd444719f6c7f4da0f13990009a009a87794eca3b98")
        self.assertNotIn("v4_land_base_factor", config.record())

    def test_v4_parameters_change_identity_and_input(self):
        default = GenerationConfig.for_profile("geographic_v4")
        shallow = GenerationConfig.for_profile("geographic_v4", v4_ocean_depth_m=40)
        self.assertNotEqual(default.identity()[0], shallow.identity()[0])
        self.assertEqual(default.cond_snr[0], .1)
        full = v4_factory(seed=20260930).sample_raw(-30, -20, 20, 30)
        split = np.concatenate((v4_factory(seed=20260930).sample_raw(-30, -20, 0, 30),
                                v4_factory(seed=20260930).sample_raw(0, -20, 20, 30)), axis=2)
        np.testing.assert_array_equal(full, split)
        self.assertTrue(np.isfinite(full).all())
        self.assertGreaterEqual(float(full[0].min()), -80)
        self.assertFalse(np.array_equal(full[0], v3_factory(seed=20260930).sample_raw(-30, -20, 20, 30)[0]))
        self.assertFalse(np.array_equal(full[0], v4_factory(seed=20260930, ocean_depth_m=40)
                                        .sample_raw(-30, -20, 20, 30)[0]))

    def test_invalid_parameters_rejected(self):
        for value in (float("nan"), float("inf"), -1, 0, 1101):
            with self.assertRaises(ValueError):
                v4_factory(seed=1, ocean_depth_m=value)
            with self.assertRaises(ValueError):
                GenerationConfig.for_profile("geographic_v4", v4_ocean_depth_m=value)
        with self.assertRaises(ValueError):
            GenerationConfig.for_profile("geographic_v3", v4_ocean_depth_m=40)

    def test_retry_uses_whole_seed_batch_and_stops_at_first_pass(self):
        jobs_seen = []
        def evaluate(directory, candidate, jobs, name):
            directory.mkdir()
            jobs_seen.append(jobs)
            return {"status": "height_fail" if len(jobs_seen) == 1 else "height_pass"}
        with tempfile.TemporaryDirectory() as temporary, \
             patch("tools.prepare_height_budget_v4.evaluate_candidate", side_effect=evaluate), \
             patch("tools.prepare_height_budget_v4.publish_batch") as publish:
            result = prepare_batch_with_retry(Path(temporary) / "batch", 7,
                                              ((0, 0), (64, 64)), ((.12, .18, 80),
                                                                     (.08, .18, 60),
                                                                     (.04, .18, 40)))
        self.assertEqual(result["selected_candidate_index"], 2)
        self.assertEqual(jobs_seen, [[(7, 0, 0), (7, 64, 64)]] * 2)
        publish.assert_called_once()

    def test_publish_rejects_incomplete_and_duplicate_batch(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            invalid = {"status": "height_pass", "jobs": [[7, 0, 0], [7, 0, 0]],
                       "samples": []}
            with self.assertRaisesRegex(ValueError, "incomplete"):
                publish_batch(directory, invalid)
            self.assertEqual(list(directory.iterdir()), [])

    def test_retry_exhaustion_and_fatal_error(self):
        with tempfile.TemporaryDirectory() as temporary:
            parent = Path(temporary)
            failed = {"status": "height_fail"}
            with patch("tools.prepare_height_budget_v4.evaluate_candidate", return_value=failed) as evaluate:
                result = prepare_batch_with_retry(parent / "exhausted", 7, ((0, 0),),
                                                  ((.12, .18, 80), (.08, .18, 60), (.04, .18, 40)))
            self.assertEqual(evaluate.call_count, 3)
            self.assertEqual(result["status"], "height_fail")
            self.assertFalse((parent / "exhausted" / "publication").exists())
            with patch("tools.prepare_height_budget_v4.evaluate_candidate",
                       side_effect=OSError("disk failed")) as evaluate:
                with self.assertRaisesRegex(OSError, "disk failed"):
                    prepare_batch_with_retry(parent / "fatal", 7, ((0, 0),),
                                             ((.12, .18, 80), (.08, .18, 60)))
            self.assertEqual(evaluate.call_count, 1)
            stored = json.loads((parent / "fatal" / "batch.json").read_text(encoding="utf-8"))
            self.assertEqual(stored["status"], "error")
            self.assertIn("disk failed", stored["error"])

    def test_publish_rechecks_full_raw_grid(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            elevation = np.zeros((513, 513), dtype=np.float32)
            elevation[0, 0] = 1000
            metadata = {"identity": "same", "seed": "7", "native_origin": [0, 0],
                        "native_resolution_m": 30}
            archive = directory / "raw.npz"
            np.savez_compressed(archive, elevation=elevation,
                                metadata=json.dumps(metadata), generation_config=json.dumps({}))
            sample = {"seed": 7, "native_origin": [0, 0], "raw_npz": archive.name,
                      "raw_sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
                      "raw_full": {"height_pass": True},
                      "processed_interior": {"height_pass": True}}
            record = {"status": "height_pass", "jobs": [[7, 0, 0]], "samples": [sample],
                      "generation_identity": "same", "generation_config": {}}
            with self.assertRaisesRegex(ValueError, "raw full grid fails"):
                publish_batch(directory, record)
            self.assertFalse((directory / "publication").exists())
            self.assertFalse((directory / "publication.staging").exists())

    def test_height_result_has_real_metre_slope(self):
        x = np.arange(513, dtype=np.float64)[None, :]
        grid = np.broadcast_to(30 * x, (513, 513))
        result = height_result(grid)
        self.assertAlmostEqual(result["slope_m_per_m_p95"], 1)

    def test_publish_manifest_hashes_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            config = GenerationConfig.for_profile("geographic_v4").record()
            identity = "same"
            samples = []
            for x in (0, 64):
                elevation = np.full((513, 513), 50, dtype=np.float32)
                metadata = {"identity": identity, "seed": "7", "native_origin": [x, 0],
                            "native_resolution_m": 30}
                archive = directory / f"raw{x}.npz"
                np.savez_compressed(archive, elevation=elevation, metadata=json.dumps(metadata),
                                    generation_config=json.dumps(config))
                samples.append({"seed": 7, "native_origin": [x, 0], "raw_npz": archive.name,
                                "raw_sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
                                "raw_full": {"height_pass": True},
                                "processed_interior": {"height_pass": True}})
            record = {"status": "height_pass", "jobs": [[7, 0, 0], [7, 64, 0]],
                      "samples": samples, "generation_identity": identity,
                      "generation_config": config}
            with patch("tools.prepare_height_budget_v4.prepare_metric_region") as prepare, \
                 patch("tools.prepare_height_budget_v4.export_metric_minecraft") as export:
                prepare.side_effect = lambda base, destination: Path(destination).mkdir()
                export.side_effect = lambda region, destination: Path(destination).write_bytes(b"snapshot")
                publish_batch(directory, record)
            manifest = json.loads((directory / "publication" / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(len(manifest["snapshot_sha256"]), 2)
            self.assertEqual(set(manifest["snapshot_sha256"].values()),
                             {hashlib.sha256(b"snapshot").hexdigest()})
            record["status"] = "height_pass"
            with self.assertRaises(FileExistsError):
                publish_batch(directory, record)

    def test_second_snapshot_failure_cleans_staging(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            config = GenerationConfig.for_profile("geographic_v4").record()
            samples = []
            for x in (0, 64):
                archive = directory / f"raw{x}.npz"
                np.savez_compressed(archive, elevation=np.full((513, 513), 50, dtype=np.float32),
                                    metadata=json.dumps({"identity": "same", "seed": "7",
                                                         "native_origin": [x, 0],
                                                         "native_resolution_m": 30}),
                                    generation_config=json.dumps(config))
                samples.append({"seed": 7, "native_origin": [x, 0], "raw_npz": archive.name,
                                "raw_sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
                                "raw_full": {"height_pass": True},
                                "processed_interior": {"height_pass": True}})
            record = {"status": "height_pass", "jobs": [[7, 0, 0], [7, 64, 0]],
                      "samples": samples, "generation_identity": "same",
                      "generation_config": config}
            with patch("tools.prepare_height_budget_v4.prepare_metric_region") as prepare, \
                 patch("tools.prepare_height_budget_v4.export_metric_minecraft") as export:
                prepare.side_effect = lambda base, destination: Path(destination).mkdir()
                calls = 0
                def export_snapshot(region, destination):
                    nonlocal calls
                    calls += 1
                    if calls == 2:
                        raise OSError("second snapshot failed")
                    Path(destination).write_bytes(b"snapshot")
                export.side_effect = export_snapshot
                with self.assertRaisesRegex(OSError, "second snapshot failed"):
                    publish_batch(directory, record)
            self.assertFalse((directory / "publication").exists())
            self.assertFalse((directory / "publication.staging").exists())


if __name__ == "__main__":
    unittest.main()
