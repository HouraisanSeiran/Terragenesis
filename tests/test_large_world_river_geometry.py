import tempfile
import unittest
import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import numpy as np

from terrain_pipeline.common_infra import file_sha256
from terrain_pipeline.surface_rivers.large_world_river_geometry import build_geometry, load, query, save
from terrain_pipeline.geology import sample_lithology_points


def make(*, runoff=1., hardness=None, unknown=False, origin=(0, 0)):
    height = np.array([[9., 8., 7.], [8., 7., 6.], [7., 6., 5.]])
    valid = np.ones((3, 3), bool)
    receiver = np.array([[1, 2, 5], [4, 5, 8], [7, 8, -1]], dtype=np.int64)
    kinds = np.where(receiver < 0, "retained", "interior").astype("U24")
    seeds = np.zeros((3, 3), bool)
    seeds[0, 0] = unknown
    topology = dict(receiver=receiver, terminal_kind=kinds, upstream_unknown_mask=seeds)

    def lithology(*args, **kwargs):
        result = sample_lithology_points(*args, **kwargs)
        if hardness is not None:
            result["bed_hardness"][:] = hardness[0]
            result["bank_hardness"][:] = hardness[1]
        return result

    with patch("terrain_pipeline.surface_rivers.large_world_river_geometry.sample_lithology_points", side_effect=lithology):
        return build_geometry(height, valid, list(origin), 20261020, {"identity": "test"},
            runoff_m_per_year=runoff, channel_threshold_m3_s=1e-6, topology=topology)


class LargeWorldRiverGeometryTest(unittest.TestCase):
    def test_same_source_q_and_bed_bank_responses(self):
        soft = make(hardness=(.2, .2))
        hard_bed = make(hardness=(.8, .2))
        hard_bank = make(hardness=(.2, .8))
        high_q = make(runoff=4., hardness=(.2, .2))
        for other in (hard_bed, hard_bank, high_q):
            np.testing.assert_array_equal(soft["arrays"]["source_elevation_m"], other["arrays"]["source_elevation_m"])
        index = (2, 2)
        a, b, c, d = (p["arrays"] for p in (soft, hard_bed, hard_bank, high_q))
        self.assertTrue(a["channel_mask"][index])
        self.assertGreater(b["channel_width_m"][index], a["channel_width_m"][index])
        self.assertLess(b["channel_depth_m"][index], a["channel_depth_m"][index])
        self.assertLess(c["channel_width_m"][index], a["channel_width_m"][index])
        self.assertGreater(c["channel_depth_m"][index], a["channel_depth_m"][index])
        self.assertGreater(d["channel_width_m"][index], a["channel_width_m"][index])
        self.assertGreater(d["channel_depth_m"][index], a["channel_depth_m"][index])

    def test_pending_and_cold_read(self):
        product = make(unknown=True)
        pending = query(product, 2, 2)
        self.assertEqual(pending["status"], "pending")
        self.assertGreater(pending["known_q_m3_s"], 0.)
        self.assertIsNone(pending["representative_q_m3_s"])
        self.assertIsNone(pending["channel_width_m"])
        self.assertTrue(np.isnan(product["arrays"]["representative_q_m3_s"][2, 2]))
        self.assertEqual(pending["derived_elevation_m"], pending["source_elevation_m"])
        self.assertEqual(query(product, 20, 20)["status"], "unresolved")
        with self.assertRaises(ValueError):
            query(product, 0.5, 0)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "geometry.npz"
            save(path, product)
            self.assertEqual(query(load(path, file_sha256(path)), 2, 2), pending)

    def test_lithology_matches_native_node_coordinates(self):
        product = make(origin=(-17, 29))
        expected = sample_lithology_points((-17 + 1) * 30., (29 + 2) * 30., world_seed=20261020)
        for key in ("rock_index", "bed_hardness", "bank_hardness"):
            self.assertEqual(product["arrays"][key][2, 1], expected[key].item())
        self.assertEqual(len(product["metadata"]["rock_table_identity"]), 64)
        self.assertEqual(len(product["metadata"]["lithology_sample_identity"]), 64)

    def test_water_does_not_receive_runoff_or_cut(self):
        height = np.array([[4., 3., 2.], [3., 2., 1.], [2., 1., 0.]])
        water = np.zeros((3, 3), bool)
        water[2, 2] = True
        product = build_geometry(height, np.ones((3, 3), bool), [0, 0], 20261020, {},
            runoff_m_per_year=1., channel_threshold_m3_s=1e-6, water_mask=water)
        a = product["arrays"]
        self.assertEqual(a["known_q_m3_s"][2, 2], 0.)
        self.assertEqual(a["bed_elevation_m"][2, 2], height[2, 2])
        self.assertEqual(query(product, 2, 2)["status"], "water")
        self.assertFalse(np.any(a["terminal_kind"] == "open_outflow"))

    def test_synthetic_layout_page_prepare_and_query_cli(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            origin = [-11, 23]
            side = 17
            metadata = {"schema": "td-native-page-v1", "native_origin": origin, "size": side,
                        "spacing_m": 30., "world_seed": 20261020,
                        "layout_identity": "synthetic-layout", "conditioning_identity": "synthetic-conditioning"}
            page = root / "native-page.npz"
            height = 100. - np.add.outer(np.arange(side), np.arange(side)).astype(float)
            np.savez(page, elevation_native=height, metadata_json=np.array(json.dumps(metadata)))
            classes = np.zeros((side, side), np.uint8)
            classes[8, 8] = 2
            class_path = root / "layout-classes.npy"
            np.save(class_path, classes)
            layout = {"layout_identity": metadata["layout_identity"],
                      "conditioning_identity": metadata["conditioning_identity"],
                      "origin_native_xz": origin, "page_side_cells": side,
                      "plan": {"seed": 20261020}, "layout_parameters": {"fixture": "synthetic"}}
            layout_path = root / "page.json"
            layout_path.write_text(json.dumps(layout), encoding="utf-8")
            output = root / "geometry.npz"
            command = [sys.executable, "tools/prepare_large_world_river_geometry.py", "--page", str(page),
                       "--page-sha256", file_sha256(page), "--origin", *map(str, origin),
                       "--shape", str(side), str(side), "--runoff-m-per-year", "1",
                       "--channel-threshold-m3-s", "0.000001", "--layout-classes", str(class_path),
                       "--layout-page-json", str(layout_path), "--output", str(output)]
            subprocess.run(command, check=True, capture_output=True, text=True)
            product = load(output, file_sha256(output))
            self.assertEqual(product["metadata"]["source"]["page_metadata"]["layout_identity"], "synthetic-layout")
            self.assertEqual(product["arrays"]["known_q_m3_s"][8, 8], 0.)
            self.assertEqual(product["arrays"]["bed_elevation_m"][8, 8], height[8, 8])
            result = subprocess.run([sys.executable, "tools/query_large_world_river_geometry.py", str(output),
                "--sha256", file_sha256(output), "--x", str(origin[0] + 8), "--z", str(origin[1] + 8)],
                check=True, capture_output=True, text=True)
            self.assertEqual(json.loads(result.stdout)["water_class"], 2)
            for key, value in (("layout_identity", "wrong"), ("origin_native_xz", [0, 0])):
                altered = dict(layout, **{key: value})
                layout_path.write_text(json.dumps(altered), encoding="utf-8")
                output.unlink(missing_ok=True)
                self.assertNotEqual(subprocess.run(command, capture_output=True).returncode, 0)


if __name__ == "__main__":
    unittest.main()
