import unittest

from terrain_pipeline.td_lake_interface_continuous_bed import (
    build_lake_interface_continuous_bed, validate_lake_interface_continuous_bed)


class LakeInterfaceContinuousBedTests(unittest.TestCase):
    def test_rejected_lake_anchor_stays_pending(self):
        geometry = {"schema": "td-watershed-geometry-preparation-v1", "identity_sha256": "a" * 64}
        patches = {"schema": "td-watershed-interface-patch-preparation-v2", "identity_sha256": "b" * 64,
                   "patches": [{"kind": "lake_anchor_transition", "patch_id": "anchor:1",
                                "status": "rejected", "rejection_reasons": ["missing_anchor_cross_section"]}]}
        result = build_lake_interface_continuous_bed(geometry, patches)
        self.assertEqual(result["status"], "pending")
        self.assertFalse(result["continuous_bed_ready"])
        validate_lake_interface_continuous_bed(result)


if __name__ == "__main__":
    unittest.main()
