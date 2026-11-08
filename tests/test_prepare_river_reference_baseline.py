"""Reference observations remain bound to primary bytes and channel groups."""

import json
from pathlib import Path
import shutil
import tempfile
import unittest

from tools.prepare_river_reference_baseline import USGS, VECTORS, measurement_reference, vector_reference


class RiverReferenceTests(unittest.TestCase):
    def test_primary_replay_keeps_group_and_depth_semantics(self):
        reference = measurement_reference(USGS / "report.json")
        self.assertEqual(sum(group["count"] for group in reference["groups"].values()), 100)
        self.assertIn("Main", reference["groups"])
        self.assertIn("main", reference["groups"])
        for group in reference["groups"].values():
            for row, depth, ratio in zip(group["records"], group["metric_samples"]["mean_depth_m"],
                                          group["metric_samples"]["width_depth_ratio"]):
                measured = row["measured_si"]
                self.assertEqual(depth, measured["channel_area"] / measured["channel_width"])
                self.assertEqual(ratio, measured["channel_width"] / depth)
            self.assertEqual(group["conditions"]["bankfull"], "not_identified")

    def test_primary_bytes_and_derived_report_tampering_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            for filename in ["report.json", "queryables.json", "measurements.json"]:
                shutil.copyfile(USGS / filename, output / filename)
            report_path = output / "report.json"
            report = json.loads(report_path.read_text(encoding="utf-8"))
            report["retained_measurements"][0]["derived_mean_depth_m"] += 1
            report_path.write_text(json.dumps(report), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "primary measurement replay"):
                measurement_reference(report_path)
            shutil.copyfile(USGS / "report.json", report_path)
            with (output / "measurements.json").open("ab") as stream:
                stream.write(b" ")
            with self.assertRaisesRegex(ValueError, "hash mismatch"):
                measurement_reference(report_path)

    def test_vector_coordinates_keep_original_reaches_and_evidence_level(self):
        original = json.loads(VECTORS.read_text(encoding="utf-8"))
        reference = vector_reference(VECTORS)
        self.assertEqual(len(original["rivers"]), len(reference["reaches"]))
        self.assertFalse(reference["policy"]["independent_centerline"])
        for source, reach in zip(original["rivers"], reference["reaches"]):
            self.assertEqual(source["parts_lon_lat"], reach["parts_lon_lat"])
            self.assertEqual([len(part) for part in source["parts_lon_lat"]],
                             [len(part) for part in reach["parts_xz_m"]])
            point = reach["parts_xz_m"][0][0]
            self.assertGreater(point[0], 100000)
            self.assertLess(point[1], -3000000)


if __name__ == "__main__":
    unittest.main()
