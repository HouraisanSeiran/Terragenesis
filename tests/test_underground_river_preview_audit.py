"""Behavioral rejection tests for independently audited saved gallery evidence."""

from copy import deepcopy
from pathlib import Path
import tempfile
import unittest

from tests import test_underground_river_v1 as fixtures
from terrain_pipeline.underground_river_v1 import build_preview
from tools.audit_underground_river_preview import ROOT, audit, check_saved_geometry
from tools.td_shared_channel_fine_saved_audit import digest


def reseal(record):
    record.pop("identity_sha256", None)
    record["identity_sha256"] = digest(record)
    return record


class SavedGalleryAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixtures.UndergroundRiverTests.setUpClass()
        cls.rock = fixtures.UndergroundRiverTests.rock
        cls.vdm = fixtures.UndergroundRiverTests.vdm
        cls.preview = build_preview(cls.rock, cls.vdm, fixtures.flat_sampler, {})

    def check(self, preview):
        return check_saved_geometry(reseal(preview), self.rock, self.vdm)

    def test_original_saved_geometry_passes_without_producer_calls(self):
        from unittest.mock import patch
        with patch("terrain_pipeline.underground_river_v1.build_preview", side_effect=AssertionError("producer called")):
            result = self.check(deepcopy(self.preview))
        self.assertTrue(result["actual_boolean"]["independent_boolean_verified"])
        self.assertTrue(result["actual_air_route"]["actual_air_polyline_verified"])

    def test_resealed_material_lie_is_rejected(self):
        altered = deepcopy(self.preview)
        altered["metrics"]["excavated_rock_m3"] += 1.
        with self.assertRaisesRegex(ValueError, "excavated material"):
            self.check(altered)

    def test_consistently_resealed_endpoint_movement_is_rejected(self):
        altered = deepcopy(self.preview)
        altered["stations"][0]["ring_local_xyz_m"][0][0] += .1
        altered["vdm"]["derived_local_xyz_m"][0][0] += .1
        altered["vdm"]["displacement_xyz_m"][0][0] += .1
        altered["meshes"]["cutter"]["vertices_local_xyz_m"][0][0] += .1
        with self.assertRaisesRegex(ValueError, "immutable portal ring"):
            self.check(altered)

    def test_resealed_air_path_and_capability_are_rejected(self):
        altered = deepcopy(self.preview)
        altered["geometry_checks"]["air_path_local_xyz_m"][3][1] -= 30.
        altered["geometry_checks"]["air_path_xyz_m"][3][1] -= 30.
        with self.assertRaisesRegex(ValueError, "waypoint outside"):
            self.check(altered)
        altered = deepcopy(self.preview)
        altered["capabilities"]["hydraulic_solved"] = True
        with self.assertRaisesRegex(ValueError, "capability promoted"):
            self.check(altered)

    def test_resealed_remaining_rock_substitution_is_rejected(self):
        altered = deepcopy(self.preview)
        altered["meshes"]["rock_after"] = deepcopy(altered["meshes"]["rock_before"])
        with self.assertRaisesRegex(ValueError, "differs from independent Boolean"):
            self.check(altered)

    def test_wrong_external_sha_is_rejected_before_parsing(self):
        with tempfile.TemporaryDirectory(dir=ROOT / "verification") as directory:
            path = Path(directory) / "index.json"
            path.write_text("{}", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "SHA256 mismatch"):
                audit({"path": str(path), "sha256": "0" * 64})


if __name__ == "__main__":
    unittest.main()
